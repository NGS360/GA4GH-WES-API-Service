# Running Workflows on AWS HealthOmics via the GA4GH WES API

A user guide for submitting, monitoring, and retrieving results from
bioinformatics workflows that execute on AWS HealthOmics through the GA4GH
Workflow Execution Service (WES) API.

**Status:** verified against the code on `main`, 2026-09-30.

---

## Table of Contents

1. [Overview](#1-overview)
2. [System Architecture](#2-system-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Submitting a Workflow](#4-submitting-a-workflow)
5. [Referencing Inputs by NGS360 File ID](#5-referencing-inputs-by-ngs360-file-id)
6. [Monitoring a Run](#6-monitoring-a-run)
7. [Retrieving Outputs](#7-retrieving-outputs)
8. [Cancelling a Run](#8-cancelling-a-run)
9. [Querying & Filtering Run History](#9-querying--filtering-run-history)
10. [Using the Python Client](#10-using-the-python-client)
11. [Run States](#11-run-states)
12. [Troubleshooting](#12-troubleshooting)
13. [Reference: API Endpoints](#13-reference-api-endpoints)

---

## 1. Overview

The GA4GH WES API Service is a thin, standards-compliant layer between client
applications (NGS360, Launcher+PAML, custom scripts) and AWS HealthOmics.
It implements the
[GA4GH WES v1.1.0](https://github.com/ga4gh/workflow-execution-service-schemas)
specification so that the same client code can target HealthOmics today and
other execution engines (Arvados, SevenBridges, internal HPCs) tomorrow without
changes.

### Why route HealthOmics jobs through WES?

AWS HealthOmics on its own has limitations that make direct integration hard:

| Limitation                     | What WES gives you                                            |
| ------------------------------ | ------------------------------------------------------------- |
| Run history cleaned after 100k | Permanent MySQL `workflow_runs` table — full audit trail      |
| AWS console access required    | Authenticated HTTP API; users never need an AWS login         |
| Bespoke API design             | Standardized GA4GH interface, NGS360-friendly                 |
| Locked into a single platform  | Same API can fan out to other engines later                   |
| Mutable workflow aliases       | The concrete version used is pinned per run                   |

---

## 2. System Architecture

```
  Client                 GA4GH WES Service                         AWS
┌─────────┐   API Call   ┌──────────────────┐   invoke    ┌──────────────┐  StartRun  ┌──────────────┐
│ NGS360  │ ───────────▶ │  GA4GH WES       │ ──────────▶ │    Lambda    │ ─────────▶ │     AWS      │
│  /CLI   │              │  (FastAPI)       │             │   function   │            │ HealthOmics  │
└─────────┘              └───┬────────┬─────┘             └──────┬───────┘            └──────┬───────┘
                             │        │                          │    ▲                      │
                             ▼        ▼ resolve workflow         │    │ invoke               ▼ status
                     ┌──────────────┐ └──▶ ┌──────────┐          │    │               ┌──────────────┐
                     │   MySQL      │      │ NGS360   │          │    └───────────────│ EventBridge  │
                     │ workflow_runs│      │   API    │          │                    └──────────────┘
                     └──────────────┘      └──────────┘          │
                             ▲                                   │
                             │  POST /internal/callbacks/omics-state-change
                             └───────────────────────────────────┘
```

One Lambda function serves both directions — WES invokes it to submit a run, and
EventBridge invokes it to deliver status changes back.

**Submission path**

1. Client submits to `POST /ga4gh/wes/v1/runs` with a workflow ID, parameters,
   engine parameters, and tags.
2. WES writes a `workflow_runs` row (state `QUEUED`) and returns a `run_id`
   immediately.
3. Still within that request, WES resolves the workflow against NGS360 (alias or
   version → HealthOmics workflow ID) and resolves any `ngs360://` inputs to
   `s3://` URIs.
4. WES invokes the Lambda function asynchronously with
   `action: "submit_workflow"`. It calls HealthOmics `StartRun`.

**Completion path**

5. HealthOmics emits run status events to EventBridge.
6. EventBridge invokes the same Lambda function, which POSTs to
   `/ga4gh/wes/v1/internal/callbacks/omics-state-change`.
7. WES updates `state`, `start_time`/`end_time`, `outputs`, `system_logs`, and
   `exit_code`.
8. Client polls `GET /runs/{run_id}` or `GET /runs/{run_id}/status`.

> WES never polls HealthOmics — a run's state only advances when a callback
> arrives, and nothing retries or reconciles if one never does. If the callback
> path is misconfigured, runs sit in `QUEUED` indefinitely even though
> HealthOmics is executing them normally.

---

## 3. Prerequisites

1. **WES service URL** — e.g. `https://wes.example.com/ga4gh/wes/v1`
2. **Credentials.** Which kind depends on the deployment's `AUTH_METHOD`:
   - `api_token` (the usual deployment): an NGS360 API token, sent as
     `Authorization: Bearer <token>`. Your token is also forwarded to NGS360 for
     the workflow and file lookups, so it needs read access to them.
   - `basic`: an NGS360-issued username and password (`curl -u`).
3. **An NGS360 workflow ID.** Workflows are registered with NGS360
   (`POST /api/v1/workflows`), which imports them into HealthOmics. You submit
   the **NGS360** workflow ID, not the raw `wf-XXXXXXXX` HealthOmics ID.
4. **A project ID.** The `ProjectId` tag is required on every submission.
5. **Inputs in S3**, readable by the HealthOmics IAM role — or NGS360 file IDs
   (see [§5](#5-referencing-inputs-by-ngs360-file-id)).
6. (Optional) Python 3.10+ for the [`wes_client.py`](../scripts/wes_client.py)
   helper.

> Outputs are written to `s3://${S3_BUCKET_NAME}/Project/{ProjectId}/`, where
> `S3_BUCKET_NAME` is configured server-side. The HealthOmics role
> (`OMICS_ROLE_ARN`, configured on the Lambda) must be able to read your inputs
> and write to that prefix. The service overwrites any `outputUri` you supply in
> `workflow_engine_parameters`.

---

## 4. Submitting a Workflow

### 4.1 Required fields

| Field                   | Description                                                             |
| ----------------------- | ----------------------------------------------------------------------- |
| `workflow_url`          | NGS360 workflow ID, optionally `:ALIAS` or `:VERSION` — e.g. `wf-abc123`, `wf-abc123:latest`, `wf-abc123:3` |
| `workflow_type`         | `WDL` or `CWL` (must match how the workflow was imported)               |
| `workflow_type_version` | e.g. `1.0` for WDL, `v1.2` for CWL                                      |
| `workflow_params`       | JSON object of inputs the workflow expects                              |
| `tags`                  | JSON object; **must include `ProjectId`**                               |

### 4.2 The `workflow_url` format

```
workflow_url ::= NGS360_WORKFLOW_ID [ ":" ALIAS_OR_VERSION ]
```

- **No suffix** — the highest registered version is used.
- **`:alias`** — resolved through NGS360's alias list, e.g. `:latest`, `:prod`.
- **`:version`** — an exact version, e.g. `:3`.
- More than one colon is an error.

It is **not** an HTTP URL, and there is **no `omics:` prefix**. Earlier revisions
of this guide showed `workflow_url=omics:wf-12345abcdef`; that form does not work
— the service would treat `omics` as the workflow ID and fail to resolve it.

Whichever form you use, the concrete version resolved at submission time is
recorded on the run as `resolved_workflow_version` (`"{workflow_id}:{version}"`),
so a run submitted against a moving alias remains reproducible after the alias
moves.

### 4.3 Optional fields

| Field                       | Use                                                                    |
| --------------------------- | ---------------------------------------------------------------------- |
| `workflow_engine`           | Recorded and echoed back; routing is determined by the NGS360 deployment record, not this field |
| `workflow_engine_version`   | Recorded and echoed back                                               |
| `workflow_engine_parameters`| HealthOmics knobs — `storageType`, `cacheId`, `priority`, `name`, ...   |
| `workflow_attachment`       | Files uploaded to the configured storage backend. Note: attachments are stored but are **not** forwarded to HealthOmics |

`workflow_engine_parameters.name`, if present, becomes the run's `TaskName` tag
and display name when you do not supply `tags.TaskName` yourself.

### 4.4 Required tags

| Tag         | Required | Notes                                                            |
| ----------- | -------- | ---------------------------------------------------------------- |
| `ProjectId` | **yes**  | Submission fails without it. Determines the S3 output prefix. Sent to HealthOmics renamed as `Project` for AWS cost allocation |
| `TaskName`  | no       | Defaults to `workflow_engine_parameters.name`, else `wes-run-{uuid}` |

Any other tags are stored as-is and are filterable.

### 4.5 Submit with `curl`

```bash
curl -X POST "https://wes.example.com/ga4gh/wes/v1/runs" \
  -H "Authorization: Bearer $NGS360_TOKEN" \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=wf-abc123:latest" \
  -F 'workflow_params={
        "fastq1": "s3://my-bucket/SampleA_1.fastq.gz",
        "fastq2": "s3://my-bucket/SampleA_2.fastq.gz",
        "reference": "s3://my-refs/hg38.fa"
      }' \
  -F 'workflow_engine_parameters={
        "name": "WGS-alignment",
        "storageType": "DYNAMIC",
        "cacheId": "1234567"
      }' \
  -F 'tags={
        "ProjectId": "P-0000000-0001",
        "TaskName": "WGS-alignment"
      }'
```

A successful response returns the WES `run_id`:

```json
{ "run_id": "5b2f8c5a-1e9c-4b1f-8a7e-3d6e2a1c0fab" }
```

That UUID is the handle for every subsequent operation.

### 4.6 A 200 does not mean the workflow started

`POST /runs` returns 200 as soon as the request is recorded. Workflow resolution
and the Lambda invoke happen inside the same request, but their failures are not
reported in the response:

- If NGS360 resolution or `ngs360://` resolution fails, the run is set to
  `SYSTEM_ERROR` with the reason in `system_logs`, and no Lambda is invoked.
- Any other error during submission is logged server-side and swallowed.

**Always check the run state after submitting** rather than treating 200 as
success:

```bash
curl -H "Authorization: Bearer $NGS360_TOKEN" \
  "https://wes.example.com/ga4gh/wes/v1/runs/$RUN_ID/status"
```

### 4.7 What you provide vs. what you get back

```text
User provides                                  →  User receives (when run completes)
{                                                 {
  "workflow_url":  "wf-abc123:latest",              "run_id": "5b2f8c5a-...",
  "workflow_params": {                              "state": "COMPLETE",
    "fastq1": "s3://.../SampleA_1.fastq.gz",        "outputs": {
    "fastq2": "s3://.../SampleA_2.fastq.gz",          "output_mapping": {
    "reference": "s3://my-refs/hg38.fa"                 "annotated_vcf": "s3://..."
  },                                                  },
  "workflow_engine_parameters": {                     "log_urls": { ... }
    "name": "WGS-alignment",                        },
    "storageType": "DYNAMIC"                        "run_log": {
  },                                                  "start_time": "...",
  "tags": { "ProjectId": "P-0000000-0001" }           "end_time": "...",
}                                                     "exit_code": 0,
                                                      "system_logs": [ ... ]
                                                    }
                                                  }
```

Note that `outputs` is **nested**: workflow outputs live under
`outputs.output_mapping`, log locations under `outputs.log_urls`.

---

## 5. Referencing Inputs by NGS360 File ID

Instead of hard-coding S3 paths you can reference NGS360 file records:

```bash
  -F 'workflow_params={
        "fastq1": "ngs360://3f2a1b4c-8d9e-4f01-a234-56789abcdef0",
        "fastq2": "ngs360://8d7e6f5a-1234-4321-bbbb-0123456789ab",
        "reference": "s3://my-refs/hg38.fa"
      }'
```

At submission, every string of the form `ngs360://<file-id>` anywhere in
`workflow_params` — including inside nested objects and arrays — is replaced with
that file's `s3://` URI, fetched from `GET /api/v1/files/{id}` using your bearer
token. Plain `s3://` values and non-string values pass through untouched.

Two things to know:

- `GET /runs/{run_id}` echoes back the **unresolved** `ngs360://` form, because
  the database stores what you submitted. Only the Lambda payload carries
  resolved URIs.
- If a file ID is unknown, inaccessible with your token, or not backed by S3, the
  run goes to `SYSTEM_ERROR` and `system_logs` names the offending ID.

---

## 6. Monitoring a Run

### Quick status

```bash
curl -H "Authorization: Bearer $NGS360_TOKEN" \
  "https://wes.example.com/ga4gh/wes/v1/runs/$RUN_ID/status"
```

```json
{ "run_id": "5b2f8c5a-...", "state": "RUNNING" }
```

### Full run log

```bash
curl -H "Authorization: Bearer $NGS360_TOKEN" \
  "https://wes.example.com/ga4gh/wes/v1/runs/$RUN_ID"
```

Returns the request as submitted, the run state, the display `name`, `outputs`,
a `task_logs_url`, and a `run_log` object with `start_time`, `end_time`,
`exit_code`, and `system_logs`.

`run_log` is `null` until the run reaches `RUNNING` (it is only populated once
`start_time` is set by a callback). `system_logs` is where resolution errors,
HealthOmics status messages, and failure reasons accumulate — read it first when
diagnosing a run.

### Per-task detail

`GET /runs/{run_id}/tasks` is implemented and spec-compliant, but **nothing
populates the `task_logs` table today**, so it returns an empty list for real
runs. For per-task detail, go to the HealthOmics run or CloudWatch.

### Polling pattern (shell)

```bash
while :; do
  STATE=$(curl -s -H "Authorization: Bearer $NGS360_TOKEN" \
    "$WES_URL/runs/$RUN_ID/status" | jq -r .state)
  echo "$(date -Iseconds)  $RUN_ID  $STATE"
  case "$STATE" in
    COMPLETE|EXECUTOR_ERROR|SYSTEM_ERROR|CANCELED) break ;;
  esac
  sleep 30
done
```

---

## 7. Retrieving Outputs

When `state == COMPLETE`, `GET /runs/{run_id}` returns:

```json
{
  "outputs": {
    "output_mapping": {
      "annotated_vcf":     "s3://my-bucket/Project/P-0000000-0001/.../SampleA.vcf.gz",
      "alignment_metrics": "s3://my-bucket/Project/P-0000000-0001/.../SampleA.metrics.txt"
    },
    "log_urls": {
      "cloudwatch": "https://console.aws.amazon.com/cloudwatch/..."
    }
  }
}
```

`output_mapping` is whatever the callback supplied, so its keys are the
workflow's declared output names. `log_urls` is populated on any terminal state,
`output_mapping` only on `COMPLETE`.

Outputs are written under
`s3://${S3_BUCKET_NAME}/Project/{ProjectId}/`, the prefix the service sets as
`outputUri`. The exact layout beneath that prefix is HealthOmics' choice, so
prefer reading `output_mapping` over constructing paths.

---

## 8. Cancelling a Run

```bash
curl -X POST -H "Authorization: Bearer $NGS360_TOKEN" \
  "https://wes.example.com/ga4gh/wes/v1/runs/$RUN_ID/cancel"
```

Only the user who submitted a run may cancel it — anyone else gets 403. Runs
already in `COMPLETE`, `EXECUTOR_ERROR`, `SYSTEM_ERROR`, or `CANCELED` cannot be
cancelled (400).

> **Current limitation.** This endpoint sets the run to `CANCELING` in the WES
> database and nothing else. It does **not** forward a cancellation to
> HealthOmics — the HealthOmics run keeps executing and keeps incurring cost, and
> the WES run stays in `CANCELING`. To actually stop a run, cancel it in
> HealthOmics (console or `aws omics cancel-run`); the resulting `CANCELLED`
> event will then move the WES run to `CANCELED`.

---

## 9. Querying & Filtering Run History

`GET /ga4gh/wes/v1/runs` accepts a `filters` query parameter (URL-encoded JSON)
that queries the persistent `workflow_runs` table:

```bash
# All RUNNING jobs in a given project
curl -H "Authorization: Bearer $NGS360_TOKEN" -G \
  --data-urlencode 'filters={"state":"RUNNING","tags":{"ProjectId":"P-0000000-0001"}}' \
  "https://wes.example.com/ga4gh/wes/v1/runs?page_size=50"
```

Filter rules:

- A scalar value matches a column for equality — e.g.
  `{"state": "COMPLETE"}`, `{"workflow_url": "wf-abc123:latest"}`,
  `{"project": "P-0000000-0001"}`, `{"task_name": "WGS-alignment"}`,
  `{"user_id": "jdoe"}`, `{"workflow_run_id": "1234567"}`.
- A nested object matches individual keys of a JSON column (`tags`,
  `workflow_params`) — e.g. `{"tags": {"ProjectId": "P-...", "TaskName": "WGS-align"}}`.
- Filter keys must name real columns. **Unrecognised keys are silently ignored**,
  as is an invalid `state` value — you get unfiltered results rather than an
  error, so check that your filter narrowed anything.
- Note `ProjectId` is the *tag* key; `project` is the *column*. Both work.

Pagination is offset-based: `page_size` defaults to 10 and is capped at 100, and
`page_token` is the opaque (numeric) `next_page_token` from the previous
response. `next_page_token` is `""` on the last page. Ordering is newest-first by
creation time, so runs created during pagination can shift rows between pages.

All authenticated users can list and read **all** runs; listing is not scoped to
your own submissions.

---

## 10. Using the Python Client

A reference client is included at [scripts/wes_client.py](../scripts/wes_client.py).

> The bundled client currently supports **HTTP Basic auth only** — it has no
> bearer-token option. Against a deployment running `AUTH_METHOD=api_token` it
> cannot authenticate; use `curl`, PAML, or the NGS360 MCP `wes_*` tools instead.

### CLI

```bash
python scripts/wes_client.py \
  --base-url "$WES_URL" --username "$WES_USER" --password "$WES_PASS" \
  submit \
  --workflow-url wf-abc123:latest \
  --workflow-type WDL --workflow-version 1.0 \
  --workflow-params '{"fastq1":"s3://my-bucket/SampleA_1.fastq.gz",
                      "fastq2":"s3://my-bucket/SampleA_2.fastq.gz",
                      "reference":"s3://my-refs/hg38.fa"}' \
  --tags '{"ProjectId":"P-0000000-0001","TaskName":"WGS-align"}'

# Status / log / cancel
python scripts/wes_client.py status  $RUN_ID
python scripts/wes_client.py log     $RUN_ID
python scripts/wes_client.py cancel  $RUN_ID

# List runs (with filters)
python scripts/wes_client.py list --page-size 20 \
  --filters '{"state":"COMPLETE","tags":{"ProjectId":"P-0000000-0001"}}'
```

### Library usage

```python
from scripts.wes_client import WESClient

client = WESClient(
    base_url="https://wes.example.com/ga4gh/wes/v1",
    username="alice",
    password="...",
)

run_id = client.submit_workflow(
    workflow_url="wf-abc123:latest",
    workflow_type="WDL",
    workflow_type_version="1.0",
    workflow_params={
        "fastq1": "s3://my-bucket/SampleA_1.fastq.gz",
        "fastq2": "s3://my-bucket/SampleA_2.fastq.gz",
        "reference": "s3://my-refs/hg38.fa",
    },
    tags={"ProjectId": "P-0000000-0001", "TaskName": "WGS-align"},
)

print(client.get_run_status(run_id))
```

### Batch submission

For sample-sheet driven batch runs, prefer the
[PAML framework](https://github.com/NGS360/PAML/) — it ships with
GA4GH WES support and handles per-sample fan-out, status aggregation, and output
collection. [scripts/run_omics_workflows.py](../scripts/run_omics_workflows.py)
is a lightweight multi-input batch runner, but note it still builds
`workflow_url` as `omics:{workflow_id}`, which the current service cannot
resolve — pass the NGS360 workflow ID form instead, or fix the script first.

---

## 11. Run States

| State              | Meaning                                                     |
| ------------------ | ----------------------------------------------------------- |
| `QUEUED`           | Recorded by WES; awaiting or during submission to HealthOmics |
| `INITIALIZING`     | Defined by the spec but never set by this service            |
| `RUNNING`          | HealthOmics reports the run as pending, queued, starting, running, stopping, or terminating |
| `PAUSED`           | Defined by the spec; not produced by HealthOmics events      |
| `COMPLETE`         | Finished successfully; `outputs.output_mapping` available, `exit_code` 0 |
| `EXECUTOR_ERROR`   | HealthOmics reported `FAILED`; `exit_code` 1                 |
| `SYSTEM_ERROR`     | Failure in WES plumbing — most often NGS360 workflow or file resolution |
| `CANCELING`        | Cancel requested through WES (see the limitation in [§8](#8-cancelling-a-run)) |
| `CANCELED`         | HealthOmics reported a `CANCELLED*` status                    |
| `UNKNOWN`          | State could not be determined                               |
| `PREEMPTED`        | In the enum for GA4GH compliance; never produced              |

Terminal states: `COMPLETE`, `EXECUTOR_ERROR`, `SYSTEM_ERROR`, `CANCELED`. Once
a run is terminal, later callbacks are acknowledged but ignored.

Because `STARTING` maps to `RUNNING`, a run goes straight from `QUEUED` to
`RUNNING` — you will not observe `INITIALIZING`.

---

## 12. Troubleshooting

| Symptom                                           | First thing to check                                                                 |
| ------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `401 Unauthorized` on submit                      | Scheme matches `AUTH_METHOD`: `Authorization: Bearer` for `api_token`, `-u` for `basic`. A deployment set to `oauth2` 401s everything — that path is unimplemented |
| `500` with "ProjectId tag is required"            | Add `ProjectId` to `tags`. (A client error reported as 500)                            |
| `SYSTEM_ERROR` right after submit                 | `system_logs` in `GET /runs/{id}` — unknown workflow ID, alias/version not found, no `AWSHealthOmics (us-east)` deployment, or an unresolvable `ngs360://` file |
| Run stuck in `QUEUED`, HealthOmics never started  | The Lambda function: `LAMBDA_FUNCTION_NAME`, invoke permissions, its CloudWatch logs    |
| Run stuck in `QUEUED`, HealthOmics *is* running   | Callback path broken: `CLIENT_ORIGIN` unset (relative callback URL), `INTERNAL_CALLBACK_API_KEY` mismatch (403s in WES logs), or the EventBridge rule |
| State never updates after HealthOmics finishes    | Same as above — the EventBridge rule targeting the Lambda for that HealthOmics account  |
| `EXECUTOR_ERROR` shortly after `RUNNING`          | Inputs not readable by `OMICS_ROLE_ARN`; parameter names don't match the workflow      |
| `EXECUTOR_ERROR` mid-run                          | `system_logs` from `GET /runs/{id}`, then the HealthOmics run and CloudWatch           |
| `outputs` empty on a `COMPLETE` run               | The callback carried no `output_mapping`; check what the Lambda POSTed                  |
| `/tasks` returns an empty list                    | Expected — `task_logs` is never populated. Use HealthOmics/CloudWatch                  |
| Run stays `CANCELING` forever                     | Expected — WES does not propagate cancels. Cancel in HealthOmics directly              |
| Filter returned everything                        | Unknown filter key or invalid `state` value; both are ignored silently                 |
| Old token still works after revocation            | Per-process token cache, up to `TOKEN_CACHE_TTL_SECONDS` per worker                    |

For deeper failure diagnosis on a specific run, use the
`pipeline-troubleshoot` skill (or your support contact) with the WES `run_id` —
it can pull HealthOmics + CloudWatch logs end-to-end.

---

## 13. Reference: API Endpoints

All endpoints are mounted under `${API_PREFIX}` (default `/ga4gh/wes/v1`) and
require authentication unless `AUTH_METHOD=none`.

### Service

| Method | Path            | Description                              |
| ------ | --------------- | ---------------------------------------- |
| GET    | `/service-info` | Supported workflow types, versions, auth, run-state counts |

### Runs

| Method | Path                       | Description                              |
| ------ | -------------------------- | ---------------------------------------- |
| POST   | `/runs`                    | Submit a new workflow run                |
| GET    | `/runs`                    | List / filter runs (paginated)           |
| GET    | `/runs/{run_id}`           | Full run log (request + state + outputs) |
| GET    | `/runs/{run_id}/status`    | Compact `{run_id, state}`                |
| POST   | `/runs/{run_id}/cancel`    | Request cancellation (owner only)        |

### Tasks

| Method | Path                             | Description                              |
| ------ | -------------------------------- | ---------------------------------------- |
| GET    | `/runs/{run_id}/tasks`           | List per-task status (currently always empty) |
| GET    | `/runs/{run_id}/tasks/{task_id}` | Task detail incl. log URLs               |

### Internal (not GA4GH)

| Method | Path                                      | Description                        |
| ------ | ----------------------------------------- | ---------------------------------- |
| POST   | `/internal/callbacks/omics-state-change`  | Lambda → WES state updates; `X-Internal-API-Key` |
| GET    | `/internal/callbacks/health`              | Callback route liveness            |

### Auto-generated docs

Swagger UI at `${API_PREFIX}/docs`, ReDoc at `${API_PREFIX}/redoc`, schema at
`${API_PREFIX}/openapi.json`.

---

## Related Documents

- [README.md](../README.md) — service install, configuration, deployment
- [docs/ARCHITECTURE.md](ARCHITECTURE.md) — internal design, DB schema, known gaps
- [docs/NGS360-Integration.md](NGS360-Integration.md) — NGS360 contracts and the callback protocol
- [docs/aws_omics_usage.md](aws_omics_usage.md) — AWS-side configuration details
- [docs/Running_Specific_HealthOmics_Workflows.md](Running_Specific_HealthOmics_Workflows.md) — batch examples
- [GA4GH WES v1.1.0 spec](https://github.com/ga4gh/workflow-execution-service-schemas)
- [PAML](https://github.com/NGS360/PAML/) — batch submission framework with GA4GH WES support
