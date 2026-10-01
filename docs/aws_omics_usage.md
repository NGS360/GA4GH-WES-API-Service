# AWS-Side Configuration for HealthOmics Execution

What has to be true on the AWS side for runs submitted to this service to reach
AWS HealthOmics and come back. For the client-facing API (how to submit, monitor,
and fetch outputs) see
[GA4GH-WES-HealthOmics-Guide.md](GA4GH-WES-HealthOmics-Guide.md).

**Status:** verified against the code on `main`, 2026-09-30.

---

## Who owns what

The WES service does **not** call HealthOmics. It invokes a Lambda function,
which calls `StartRun`. That split determines where each piece of configuration
lives:

| Concern                              | Owner                        |
| ------------------------------------ | ---------------------------- |
| HealthOmics region, `StartRun` call  | Lambda function              |
| HealthOmics IAM role (`OMICS_ROLE_ARN`) | Lambda function           |
| Workflow import into HealthOmics     | NGS360 (`POST /api/v1/workflows`) |
| Output S3 prefix (`outputUri`)       | WES service (`S3_BUCKET_NAME`) |
| Lambda name/region, callback secret  | WES service                  |
| Status events → WES                  | EventBridge → Lambda function |

The **same** Lambda function handles both directions. WES invokes it with
`action: "submit_workflow"` to start a run, and EventBridge invokes it on
HealthOmics status changes so it can POST them back to the WES callback
endpoint. There is one function, one IAM role, and one CloudWatch log group —
`LAMBDA_FUNCTION_NAME` names it.

> `OMICS_REGION` and `OMICS_ROLE_ARN` are **not read by this service**. Setting
> them in the WES `.env` does nothing; they belong to the Lambda's configuration.
> Earlier revisions of this document told you to set them here, along with
> `WORKFLOW_EXECUTOR=omics` (dead config — there is no executor switch) and a
> typo'd `S#_BUCKET_NAME`.

## WES service configuration

The AWS-relevant subset of `.env` (see [.env.example](../.env.example) for the
full list):

```bash
# Lambda function — read from os.environ directly, not via Settings
LAMBDA_FUNCTION_NAME=ngs360-workflow-lambda
LAMBDA_REGION=us-east-1

# HealthOmics output prefix: s3://$S3_BUCKET_NAME/Project/{ProjectId}/
# Bare bucket name, no s3:// scheme, no trailing slash.
S3_BUCKET_NAME=your-output-bucket
S3_REGION=us-east-1

# Callback path back from HealthOmics
CLIENT_ORIGIN=https://wes.example.com
ENABLE_CALLBACK_ENDPOINT=true
INTERNAL_CALLBACK_API_KEY=<must match the Lambda function>

# Workflow + file resolution, and token validation
NGS360_API_URL=https://ngs360.example.com
AUTH_METHOD=api_token
```

`S3_BUCKET_NAME` does double duty: the attachment bucket when
`STORAGE_BACKEND=s3`, and the HealthOmics output prefix in all cases.

## IAM

**The WES service's role** (EC2 instance profile / ECS task role) needs:

| Action                             | Resource                                   |
| ---------------------------------- | ------------------------------------------ |
| `lambda:InvokeFunction`            | the Lambda function                        |
| `secretsmanager:GetSecretValue`    | the `ENV_SECRETS` secret, if used          |
| `s3:PutObject`, `s3:GetObject`     | `S3_BUCKET_NAME`, only if `STORAGE_BACKEND=s3` |

It needs **no** `omics:*` permissions.

**The HealthOmics run role** (`OMICS_ROLE_ARN`, passed by the Lambda) needs to:

- read every input URI in `workflow_params` (after `ngs360://` resolution)
- write under `s3://${S3_BUCKET_NAME}/Project/{ProjectId}/`
- write logs to CloudWatch
- read the ECR images the workflow references

**The Lambda function's role** needs `omics:StartRun`, `omics:GetRun`, and
`iam:PassRole` on the HealthOmics run role. Because the same function also
handles the EventBridge-triggered status path, it needs outbound network access
to this service's `CLIENT_ORIGIN` and the `INTERNAL_CALLBACK_API_KEY` value.

## Output location

Outputs land under:

```
s3://${S3_BUCKET_NAME}/Project/{ProjectId}/
```

The service sets this as `workflow_engine_parameters.outputUri` and **overwrites**
any value the client supplied. The prefix is keyed on the `ProjectId` tag, not on
the run ID — which is why `ProjectId` is a required tag. The layout beneath that
prefix is HealthOmics' choice, so read `outputs.output_mapping` from
`GET /runs/{run_id}` rather than constructing paths.

## Events back into WES

Runs only leave `QUEUED` because of a callback. Wire this once per HealthOmics
account:

1. An EventBridge rule on source `aws.omics`, detail-type
   `Run Status Change`.
2. Target: the same Lambda function named by `LAMBDA_FUNCTION_NAME` — the one
   WES invokes to submit runs. It dispatches on the incoming event, so no second
   function is involved.
3. It POSTs to
   `${CLIENT_ORIGIN}${API_PREFIX}/internal/callbacks/omics-state-change` with the
   `X-Internal-API-Key` header.

The payload schema, status mapping, and response codes are specified in
[NGS360-Integration.md §6](NGS360-Integration.md#6-inbound-state-change-callback).

Verify the path is live:

```bash
curl -s https://wes.example.com/ga4gh/wes/v1/internal/callbacks/health
# {"status":"healthy","endpoint":"callbacks"}
```

## Submitting a run

`workflow_url` is an **NGS360 workflow ID** with an optional alias or version —
`NGS360WORKFLOWID[:ALIAS_OR_VERSION]`. There is no `omics:` prefix, and it is not
a raw HealthOmics `wf-XXXXXXXX` ID; NGS360 maps the registered workflow to its
HealthOmics ARN at submission time.

```bash
curl -X POST "https://wes.example.com/ga4gh/wes/v1/runs" \
  -H "Authorization: Bearer $NGS360_TOKEN" \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=wf-abc123:latest" \
  -F 'workflow_params={"input_file":"s3://your-bucket/input.fastq",
                       "reference_genome":"s3://your-bucket/reference.fa"}' \
  -F 'workflow_engine_parameters={"storageType":"DYNAMIC"}' \
  -F 'tags={"ProjectId":"P-0000000-0001","TaskName":"variant-calling"}'
```

HealthOmics-specific knobs (`storageType`, `storageCapacity`, `cacheId`,
`priority`, `name`) go in `workflow_engine_parameters` and are forwarded to
`StartRun` — except `outputUri`, which the service always sets itself.

## Cost and quota notes

- HealthOmics bills per run on compute and storage. `storageType: DYNAMIC` is
  usually cheaper than a fixed `storageCapacity`.
- The `ProjectId` tag is sent to HealthOmics renamed to `Project`, which is the
  AWS cost-allocation tag key — activate it in Billing to get per-project cost
  reports.
- `POST /runs/{id}/cancel` does **not** stop the HealthOmics run (see
  [ARCHITECTURE.md §14](ARCHITECTURE.md#14-known-gaps--limitations)). A run
  "cancelled" through WES keeps billing until it is cancelled in HealthOmics.
- HealthOmics prunes its own run history; the WES `workflow_runs` table is the
  durable record. Completed runs are retained deliberately — do not add automatic
  cleanup, the history is used downstream for workflow performance evaluation.

## Logs

| Where                      | What                                             |
| -------------------------- | ------------------------------------------------ |
| `GET /runs/{id}` → `system_logs` | Resolution errors, HealthOmics status messages, failure reasons |
| `outputs.log_urls`         | Log locations supplied by the callback            |
| Lambda function CloudWatch | Both why `StartRun` failed and why a state change never arrived — the submit and EventBridge invocations share one log group, so filter by invocation |
| HealthOmics run / CloudWatch | Per-task detail. `GET /runs/{id}/tasks` is always empty — `task_logs` is never populated |

## Troubleshooting

| Symptom                                       | Check                                                                 |
| --------------------------------------------- | --------------------------------------------------------------------- |
| `SYSTEM_ERROR` immediately                    | `system_logs`: workflow ID, alias/version, or `ngs360://` file unresolvable, or no `AWSHealthOmics (us-east)` deployment |
| Stuck `QUEUED`, nothing in HealthOmics        | `LAMBDA_FUNCTION_NAME`, `lambda:InvokeFunction`, the Lambda's logs      |
| Stuck `QUEUED`, HealthOmics running           | `CLIENT_ORIGIN` unset (relative callback URL), key mismatch (403s in WES logs), EventBridge rule |
| `EXECUTOR_ERROR` right after `RUNNING`        | `OMICS_ROLE_ARN` can't read the inputs, or parameter names don't match  |
| Outputs written somewhere unexpected          | `S3_BUCKET_NAME` is a bare bucket name; the prefix is `/Project/{ProjectId}/` |
| `500 ProjectId tag is required`               | Add `ProjectId` to `tags`                                              |

## Related

- [GA4GH-WES-HealthOmics-Guide.md](GA4GH-WES-HealthOmics-Guide.md) — user guide
- [NGS360-Integration.md](NGS360-Integration.md) — Lambda payload and callback contracts
- [ARCHITECTURE.md](ARCHITECTURE.md) — internal design and known gaps
- [Running_Specific_HealthOmics_Workflows.md](Running_Specific_HealthOmics_Workflows.md) — batch submission
