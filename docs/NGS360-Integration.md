# NGS360 & AWS Integration Reference

**Audience:** engineers maintaining the WES service, the workflow-executor
Lambda, or the NGS360 API endpoints this service depends on.

**Status:** matches the code on `main`. Last verified 2026-09-30.

This document specifies the contracts that cross a process boundary. For the
internal design see [ARCHITECTURE.md](ARCHITECTURE.md); for end-user submission
instructions see [GA4GH-WES-HealthOmics-Guide.md](GA4GH-WES-HealthOmics-Guide.md).

---

## Table of Contents

1. [Contract map](#1-contract-map)
2. [Outbound: NGS360 auth](#2-outbound-ngs360-auth)
3. [Outbound: workflow resolution](#3-outbound-workflow-resolution)
4. [Outbound: file ID resolution](#4-outbound-file-id-resolution)
5. [Outbound: Lambda invocation](#5-outbound-lambda-invocation)
6. [Inbound: state-change callback](#6-inbound-state-change-callback)
7. [Deployment checklist](#7-deployment-checklist)
8. [Changing a contract](#8-changing-a-contract)

---

## 1. Contract map

| Direction | Peer            | Contract                                             |
| --------- | --------------- | ---------------------------------------------------- |
| Outbound  | NGS360 API      | `GET /api/v1/auth/me`                                |
| Outbound  | NGS360 API      | `GET /api/v1/workflows/{workflow_id}`                |
| Outbound  | NGS360 API      | `GET /api/v1/files/{file_id}`                        |
| Outbound  | AWS Lambda      | `Invoke` with `InvocationType=Event`                 |
| Outbound  | AWS Secrets Mgr | `GetSecretValue` on `$ENV_SECRETS`                   |
| Inbound   | AWS Lambda      | `POST {API_PREFIX}/internal/callbacks/omics-state-change` |

The two AWS Lambda rows are the **same function** — the one `LAMBDA_FUNCTION_NAME`
names. WES invokes it to submit a run; EventBridge invokes it on a HealthOmics
status change and it calls back here. So sections [5](#5-outbound-lambda-invocation)
and [6](#6-inbound-state-change-callback) are two contracts with one peer, and a
change to either is a change to that one function.

Every outbound NGS360 request carries:

```http
X-Client-Application: ngs360-ga4gh
User-Agent: ngs360-ga4gh/1.0
Authorization: Bearer <caller's token>      # only when the caller supplied one
```

The bearer token is the **end user's** token, forwarded verbatim from the
inbound request (`get_bearer_token` → `CurrentToken` → `submit_workflow`). The
WES service has no service account of its own for NGS360 reads. If the caller
authenticated with Basic auth or `AUTH_METHOD=none`, outbound calls are
anonymous and NGS360 must permit that or the submission fails with
`SYSTEM_ERROR`.

---

## 2. Outbound: NGS360 auth

Used only when `AUTH_METHOD=api_token`.

```http
GET {NGS360_API_URL}/api/v1/auth/me
Authorization: Bearer <token>
```

Expected response — anything with a non-empty `username`:

```json
{ "username": "jdoe" }
```

WES behaviour:

| Outcome                      | Result                                         |
| ---------------------------- | ---------------------------------------------- |
| 200 with `username`          | Identity established; cached for `TOKEN_CACHE_TTL_SECONDS` |
| 200 without `username`       | 401 `Could not determine username from token`  |
| Any non-200                  | 401 `Invalid or expired API token`             |
| Connection error / timeout (10 s) | 503 `Authentication service unavailable: ...` |

Results are cached in a process-local `TTLCache` keyed on the raw token. A
revoked token stays usable for up to the TTL on each worker — shorten
`TOKEN_CACHE_TTL_SECONDS` if that window matters, or call `invalidate_token()`.

---

## 3. Outbound: workflow resolution

```http
GET {NGS360_API_URL}/api/v1/workflows/{workflow_id}
```

### Fields WES reads

The response is a workflow object. WES depends on exactly these paths:

```jsonc
{
  "versions": [                       // required, non-empty
    {
      "version": 2,                   // required — compared with max() and str() ==
      "deployments": [                // required on the selected version
        {
          "id": "...",                // used only in error messages
          "engine": "AWSHealthOmics (us-east)",   // exact-match filter
          "external_id": "arn:aws:omics:us-east-1:123:workflow/456/version/v2",
          "created_at": "2026-09-01T12:00:00"     // ISO 8601, datetime.fromisoformat
        }
      ]
    }
  ],
  "aliases": [                        // optional
    { "alias": "latest", "version": 2 }
  ]
}
```

Anything else in the payload is ignored.

### Selection algorithm

Given `workflow_url = NGS360_WORKFLOW_ID[:ALIAS_OR_VERSION]`:

1. **Parse.** Zero colons → no suffix. One colon → suffix. Two or more →
   `RuntimeError: Workflow URL format error - expect NGS360WORKFLOWID[:ALIAS_OR_VERSION]`.
2. **Version.**
   - No suffix → `max(versions, key=version)`.
   - Suffix → first `aliases[].alias == suffix`, resolving through to the
     matching `versions[]` entry; if no alias matches, an exact
     `str(versions[].version) == suffix` match; otherwise
     `RuntimeError: Specified Alias/Version {suffix} is not found ...`.
3. **Deployment.** Filter the selected version's `deployments[]` to
   `engine == "AWSHealthOmics (us-east)"`, then pick the newest `created_at`.
   Empty → `RuntimeError: Specified Alias/Version {suffix} has no deployments in
   AWSHealthOmics (us-east).`
4. **Result.** `external_id` becomes the Lambda payload's `workflow_id`;
   `"{workflow_id}:{version}"` is persisted as `resolved_workflow_version`.

> The engine label `"AWSHealthOmics (us-east)"` is hard-coded in
> `WorkflowSubmissionService._select_deployment`. Renaming that engine in NGS360,
> or deploying to a second region, requires a code change here.

### Why `resolved_workflow_version` exists

Aliases and "highest version" are mutable. Recording the concrete version at
submission time makes a run reproducible and auditable after the alias has
moved. It is written immediately after resolution, before the Lambda invoke, so
it is present even if submission later fails.

### Error handling

Any non-200 raises
`RuntimeError: NGS360 API returned status {code}: {body}`. All `RuntimeError`s
from resolution are caught by `submit_workflow`, which sets the run to
`SYSTEM_ERROR`, appends
`Failed to retrieve engine_id from NGS360 API for workflow {url}: {reason}` to
`system_logs`, and returns **without** invoking Lambda.

---

## 4. Outbound: file ID resolution

Clients may pass NGS360 file IDs instead of S3 paths. Any string in
`workflow_params` matching `ngs360://<file-id>` is resolved before submission.

```http
GET {NGS360_API_URL}/api/v1/files/{file_id}
```

WES reads exactly one field:

```json
{ "uri": "s3://bucket/path/to/SampleA_R1.fastq.gz" }
```

### Traversal rules

`workflow_params` is walked recursively:

- **dict** → each value resolved
- **list** → each element resolved
- **string** starting with `ngs360://` → replaced by the resolved `uri`
- anything else → returned unchanged

Lookups are memoised per submission, so a file ID repeated across parameters
costs one HTTP call.

Example:

```jsonc
// submitted
{
  "fastq1": "ngs360://3f2a1b4c-...",
  "fastq2": "ngs360://8d7e6f5a-...",
  "reference": "s3://my-refs/hg38.fa",
  "sample": { "bams": ["ngs360://1111-...", "s3://direct/path.bam"] },
  "threads": 8
}

// sent to Lambda as "parameters"
{
  "fastq1": "s3://ngs360-data/.../SampleA_R1.fastq.gz",
  "fastq2": "s3://ngs360-data/.../SampleA_R2.fastq.gz",
  "reference": "s3://my-refs/hg38.fa",
  "sample": { "bams": ["s3://ngs360-data/.../x.bam", "s3://direct/path.bam"] },
  "threads": 8
}
```

The **database keeps the unresolved form** in `workflow_params`; only the Lambda
payload carries resolved URIs. `GET /runs/{id}` therefore echoes back what the
client submitted, `ngs360://` and all.

### Errors

| Condition                       | `system_logs` message                                          |
| ------------------------------- | -------------------------------------------------------------- |
| 404                             | `NGS360 file '{id}' not found`                                 |
| Other non-200                   | `NGS360 API error ({code}) for file '{id}': {detail}` — `detail` from the JSON `detail` key when present, else raw body |
| `uri` absent or not `s3://`     | `NGS360 file '{id}' is not backed by S3 (uri='...')`           |

All are wrapped as
`Failed to resolve NGS360 file in workflow_params: {reason}`, set the run to
`SYSTEM_ERROR`, and skip the Lambda invoke.

---

## 5. Outbound: Lambda invocation

```python
lambda_client.invoke(
    FunctionName=os.environ["LAMBDA_FUNCTION_NAME"],
    InvocationType="Event",          # async, fire-and-forget
    Payload=json.dumps(payload),
)
```

`LAMBDA_FUNCTION_NAME` and `LAMBDA_REGION` (default `us-east-1`) are read from
`os.environ` directly in `LambdaWorkflowSubmissionService.__init__` — they are
**not** declared on the `Settings` class, so they will not appear in the startup
settings log and are not documented by `pydantic-settings`. Credentials come
from the default boto3 chain (instance role in deployment).

Because the invocation is `Event`, the Lambda's return value is discarded and
the WES service learns nothing about the outcome except through the callback.

### Payload schema

```jsonc
{
  "action": "submit_workflow",        // constant
  "source": "ga4ghwes",              // constant, lets Lambda distinguish callers
  "wes_run_id": "5b2f8c5a-1e9c-4b1f-8a7e-3d6e2a1c0fab",
  "workflow_id": "arn:aws:omics:us-east-1:123:workflow/456/version/v2",
  "workflow_version": null,          // workflow_params.workflow_version, if the client set it
  "workflow_type": "WDL",
  "parameters": { /* workflow_params, ngs360:// resolved */ },
  "workflow_engine_parameters": {
    "outputUri": "s3://my-bucket/Project/P-0000000-0001/",
    "storageType": "DYNAMIC"
  },
  "tags": {
    "Project": "P-0000000-0001",     // renamed from ProjectId
    "TaskName": "WGS-alignment",
    "WESRunId": "5b2f8c5a-...",
    "callback_url": "https://wes.example.com/ga4gh/wes/v1/internal/callbacks/omics-state-change"
  }
}
```

Three details that surprise people:

1. **`ProjectId` → `Project`.** The outgoing tag key is renamed so the
   HealthOmics run carries the AWS cost-allocation tag key `Project`. The
   database row keeps `ProjectId`. Filters on `GET /runs` use `ProjectId`.
2. **`workflow_version` comes from `workflow_params`,** not from the
   `workflow_url` suffix and not from `resolved_workflow_version`. It is
   `null` unless the client put a `workflow_version` key inside
   `workflow_params`. The authoritative version is already baked into
   `workflow_id`.
3. **`callback_url` is `CLIENT_ORIGIN` + `API_PREFIX` + the callback path.**
   If `CLIENT_ORIGIN` is unset the URL is relative (`/ga4gh/wes/v1/...`) and the
   Lambda cannot call back — runs then stay `QUEUED` forever. `CLIENT_ORIGIN`
   must be the externally reachable origin of this service, e.g.
   `https://wes.example.com`, with no trailing slash.

### Output location

`workflow_engine_parameters.outputUri` is set by the WES service to
`s3://{S3_BUCKET_NAME}/Project/{ProjectId}/`, overwriting any client-supplied
value. The HealthOmics IAM role (`OMICS_ROLE_ARN`, configured on the Lambda
side) must be able to write there and to read every input URI in `parameters`.

---

## 6. Inbound: state-change callback

```http
POST {API_PREFIX}/internal/callbacks/omics-state-change
Content-Type: application/json
X-Internal-API-Key: <shared secret>
```

This endpoint is **not part of GA4GH WES**. It exists so HealthOmics state
changes can be pushed into the WES database instead of polled: HealthOmics emits
them to EventBridge, which invokes the Lambda function — the same one
[§5](#5-outbound-lambda-invocation) describes WES invoking to submit runs — and
it POSTs them here.

### Authentication

The `X-Internal-API-Key` header is compared against
`INTERNAL_CALLBACK_API_KEY` (env var, or the same key inside the
`ENV_SECRETS` secret).

| Condition                            | Status |
| ------------------------------------ | ------ |
| `ENABLE_CALLBACK_ENDPOINT=false`     | 503    |
| `INTERNAL_CALLBACK_API_KEY` empty    | 500    |
| Header present but wrong             | 403    |
| Header absent                        | 422    |

The comparison is a plain `!=`. The key is a bearer-equivalent secret: it grants
the ability to set arbitrary state on any run, so restrict the endpoint at the
network layer as well.

### Request body

```jsonc
{
  "wes_run_id": "5b2f8c5a-1e9c-4b1f-8a7e-3d6e2a1c0fab",  // required, exactly 36 chars
  "status": "RUNNING",                                    // required, enum below
  "event_time": "2026-09-30T14:03:21Z",                   // required
  "omics_run_id": "1234567",                              // optional, 1-50 chars
  "event_id": "8f1c...",                                  // optional, 1-100 chars
  "status_message": "...",                                // optional, ≤1000 chars
  "failure_reason": "...",                                // optional, ≤2000 chars
  "output_mapping": { "vcf": "s3://..." },                // optional
  "log_urls": { "cloudwatch": "https://..." }             // optional
}
```

`status` must be one of (`OmicsRunStatus`):
`COMPLETED`, `FAILED`, `CANCELLED`, `CANCELLED_RUNNING`, `CANCELLED_STARTING`,
`RUNNING`, `STARTING`, `PENDING`, `QUEUED`, `STOPPING`, `TERMINATING`.
Anything else is a 422 from schema validation; a value that is in the enum but
somehow unmapped yields 400.

Note the two spellings: HealthOmics uses `CANCELLED` (two Ls), WES state is
`CANCELED` (one L).

### Status mapping

| HealthOmics status | WES state |
| ------------------ | --------- |
| `PENDING`, `QUEUED`, `STARTING`, `RUNNING`, `STOPPING`, `TERMINATING` | `RUNNING` |
| `COMPLETED` | `COMPLETE` |
| `FAILED` | `EXECUTOR_ERROR` |
| `CANCELLED`, `CANCELLED_RUNNING`, `CANCELLED_STARTING` | `CANCELED` |

`STARTING` maps to `RUNNING`, not `INITIALIZING` — nothing in the system ever
sets `INITIALIZING`.

### Response

```json
{
  "success": true,
  "wes_run_id": "5b2f8c5a-...",
  "previous_state": "QUEUED",
  "new_state": "RUNNING",
  "message": "Successfully updated state from QUEUED to RUNNING",
  "already_processed": false
}
```

| Situation                          | Status | `message`                                  |
| ---------------------------------- | ------ | ------------------------------------------ |
| State advanced                     | 200    | `Successfully updated state from X to Y`   |
| `event_id` already seen            | 200    | `Event {id} already processed`, `already_processed: true` |
| Mapped state equals current state  | 200    | `No state change`                          |
| Run already terminal               | 200    | `Run already in terminal state X`          |
| Unknown `wes_run_id`               | 404    | —                                          |
| Illegal transition from non-terminal | 400  | `Invalid state transition: X -> Y`         |

### Idempotency

Send `event_id` (the EventBridge event ID). It is stored in `last_event_id`, and
a repeat of the **immediately preceding** event short-circuits. This is a
single-slot check, not a full dedup log: replaying an older event after a newer
one has arrived is not detected by `event_id` — it is caught only by the
transition rules and the terminal-state guard.

EventBridge delivers at-least-once, so always send `event_id`.

### Side effects on a successful update

- `state`, `last_callback_time = event_time`, `last_event_id = event_id`
- `workflow_run_id` backfilled from `omics_run_id` if it was empty
- first `RUNNING` event sets `start_time = event_time`
- `status_message` appended to `system_logs` as `Status: ...`
- `failure_reason` appended as `Failure reason: ...`
- on any terminal state: `end_time` (if unset), `outputs.log_urls` from
  `log_urls`, `exit_code = 0` for `COMPLETE` else `1`
- on `COMPLETE`: `outputs.output_mapping` from `output_mapping`

So `GET /runs/{id}` exposes outputs **nested**, as
`{"outputs": {"output_mapping": {...}, "log_urls": {...}}}` — not as a flat map
of output name to URI.

### Health probe

```http
GET {API_PREFIX}/internal/callbacks/health
```

Unauthenticated, returns `{"status": "healthy", "endpoint": "callbacks"}`. It
does not check the database or the API key configuration.

---

## 7. Deployment checklist

For a deployment where runs actually reach HealthOmics and come back:

- [ ] `NGS360_API_URL` points at the right NGS360 environment.
- [ ] `AUTH_METHOD=api_token` so caller tokens exist to forward to NGS360.
- [ ] `LAMBDA_FUNCTION_NAME` set (and `LAMBDA_REGION` if not `us-east-1`).
- [ ] The task/instance role may `lambda:InvokeFunction` on that function.
- [ ] `S3_BUCKET_NAME` set — used for the HealthOmics `outputUri` prefix.
- [ ] `CLIENT_ORIGIN` set to this service's externally reachable origin, **no
      trailing slash**. Without it the Lambda gets a relative `callback_url`.
- [ ] `INTERNAL_CALLBACK_API_KEY` set here **and** in the Lambda function, and
      they match. Via `ENV_SECRETS` in deployed environments.
- [ ] `ENABLE_CALLBACK_ENDPOINT=true`.
- [ ] `ENV_SECRETS` names the Secrets Manager secret holding
      `SQLALCHEMY_DATABASE_URI` and `INTERNAL_CALLBACK_API_KEY`; the role may
      `secretsmanager:GetSecretValue` on it.
- [ ] `alembic upgrade head` has run (current head: `dd9d7ebae80e`).
- [ ] The NGS360 workflow has a deployment whose engine is exactly
      `AWSHealthOmics (us-east)`.
- [ ] EventBridge rule → the Lambda function → this endpoint is wired for the
      HealthOmics account running the jobs. It is the same function
      `LAMBDA_FUNCTION_NAME` names, not a second one.

Quick smoke test after deploying:

```bash
curl -s https://wes.example.com/healthcheck
curl -s https://wes.example.com/ga4gh/wes/v1/internal/callbacks/health
curl -s -H "Authorization: Bearer $NGS360_TOKEN" \
  https://wes.example.com/ga4gh/wes/v1/service-info | jq .system_state_counts
```

---

## 8. Changing a contract

Places to touch when a peer contract moves:

| Change                                  | Files to update                                              |
| --------------------------------------- | ------------------------------------------------------------ |
| NGS360 workflow JSON shape              | `services/workflow_submission_service.py` (`_select_version`, `_select_deployment`, `_find_version_by_*`) |
| New / renamed HealthOmics engine label  | `_select_deployment` (hard-coded string)                     |
| New HealthOmics status value            | `schemas/callback.py` (`OmicsRunStatus`) **and** `services/callback_service.py` (`OMICS_STATUS_MAP`) — both, or you get a 422/400 |
| New callback field                      | `schemas/callback.py`, then `CallbackService._apply_state_update` |
| New Lambda payload key                  | `submit_workflow`, and the Lambda in lockstep                |
| New persisted column                    | `db/models.py` + a new Alembic revision off the current head |
| Allowed state transitions               | `CallbackService._is_valid_transition`, `TERMINAL_STATES`     |
| New setting                             | `config.py`, `.env.example`, and the table in [ARCHITECTURE.md §11](ARCHITECTURE.md#11-configuration) |

`OmicsRunStatus` and `OMICS_STATUS_MAP` are two lists of the same statuses in
two files. They must be kept in sync by hand; there is no test asserting they
match.

---

## Related Documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — internal design, database schema, known gaps
- [GA4GH-WES-HealthOmics-Guide.md](GA4GH-WES-HealthOmics-Guide.md) — end-user submission guide
- [README.md](../README.md) — install and configuration
