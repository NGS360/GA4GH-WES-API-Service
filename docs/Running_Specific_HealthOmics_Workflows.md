# Running Batches of Workflows on HealthOmics

Patterns for submitting the same workflow across many samples through the GA4GH
WES API. For the single-run walkthrough see
[GA4GH-WES-HealthOmics-Guide.md](GA4GH-WES-HealthOmics-Guide.md); for AWS-side
setup see [aws_omics_usage.md](aws_omics_usage.md).

**Status:** verified against the code on `main`, 2026-09-30.

---

## Prerequisites

1. The workflow is registered in NGS360 and has a deployment whose engine is
   exactly `AWSHealthOmics (us-east)`. You submit the **NGS360 workflow ID**, not
   a raw HealthOmics `wf-XXXXXXXX` ID.
2. An NGS360 API token (`AUTH_METHOD=api_token` deployments) or Basic credentials
   (`AUTH_METHOD=basic`).
3. A project ID — the `ProjectId` tag is required on every submission.
4. Inputs in S3 readable by the HealthOmics run role, or NGS360 file IDs
   (`ngs360://<file-id>`).

No WES-side executor configuration is needed. There is no `WORKFLOW_EXECUTOR`
setting; submission is always Lambda-based.

## Method 1: Launcher + PAML (recommended)

For real sample-sheet driven batches, use
[PAML](https://github.com/NGS360/PAML/) with the
[WGS Launcher](https://github.com/bms-ips/WGS-Launcher-new/). PAML has GA4GH WES
support built in and handles per-sample fan-out, status aggregation, retries, and
output collection — none of which the scripts in this repo do.

## Method 2: A shell loop

Simple, dependency-free, and correct against the current API:

```bash
WES_URL=https://wes.example.com/ga4gh/wes/v1
WORKFLOW=wf-abc123:latest
PROJECT=P-0000000-0001

for SAMPLE in sample1 sample2 sample3; do
  RUN_ID=$(curl -s -X POST "$WES_URL/runs" \
    -H "Authorization: Bearer $NGS360_TOKEN" \
    -F "workflow_type=WDL" \
    -F "workflow_type_version=1.0" \
    -F "workflow_url=$WORKFLOW" \
    -F "workflow_params={\"input_file\":\"s3://your-bucket/${SAMPLE}.fastq\",
                         \"reference_genome\":\"s3://references/genome.fasta\",
                         \"threads\":8}" \
    -F "workflow_engine_parameters={\"storageType\":\"DYNAMIC\"}" \
    -F "tags={\"ProjectId\":\"$PROJECT\",\"TaskName\":\"vc-${SAMPLE}\"}" \
    | jq -r .run_id)
  echo "$SAMPLE -> $RUN_ID"
  echo "$SAMPLE $RUN_ID" >> run_ids.txt
done
```

A `200` from `POST /runs` means the request was recorded, **not** that the
workflow started. Check each run's state afterwards:

```bash
while read -r SAMPLE RUN_ID; do
  STATE=$(curl -s -H "Authorization: Bearer $NGS360_TOKEN" \
    "$WES_URL/runs/$RUN_ID/status" | jq -r .state)
  printf '%-12s %s  %s\n' "$SAMPLE" "$RUN_ID" "$STATE"
done < run_ids.txt
```

Any run showing `SYSTEM_ERROR` failed before reaching HealthOmics — read
`system_logs` from `GET /runs/{run_id}`.

## Method 3: Poll the whole batch with a filter

Because every run in the batch shares a `ProjectId` tag, you can watch them all
with one request instead of N:

```bash
curl -s -H "Authorization: Bearer $NGS360_TOKEN" -G \
  --data-urlencode 'filters={"tags":{"ProjectId":"P-0000000-0001"}}' \
  "$WES_URL/runs?page_size=100" \
  | jq -r '.runs[] | "\(.state)\t\(.run_id)\t\(.name)"' | sort
```

Give each batch a distinctive `TaskName` prefix if you need to separate batches
within one project. Note that unknown filter keys are silently ignored, so
confirm the result set actually narrowed.

## Method 4: `scripts/run_omics_workflows.py`

[scripts/run_omics_workflows.py](../scripts/run_omics_workflows.py) is a
multi-input batch runner kept in the repo, but it **does not work against the
current service** without edits. Three problems:

| Line | Problem                                                                 |
| ---- | ----------------------------------------------------------------------- |
| ~120 | Builds `workflow_url = f"omics:{workflow_id}"`. The `omics:` prefix is not part of the URL grammar; resolution fails with a workflow-URL format error |
| ~200 | Calls `WESClient(url=...)`; the constructor parameter is `base_url`, so this raises `TypeError` |
| —    | Sends no `tags`, so submission fails with "ProjectId tag is required"   |

It also inherits `wes_client.py`'s Basic-auth-only limitation, so it cannot
authenticate against an `AUTH_METHOD=api_token` deployment at all.

Use Method 1 or 2 instead, or fix the script first: pass the NGS360 workflow ID
through unchanged, rename the kwarg to `base_url`, add a `--project-id` argument
threaded into `tags`, and add bearer-token support.

## Method 5: NGS360 MCP tools

If you are working through an assistant with the NGS360 MCP server available, the
`wes_run_workflow`, `wes_get_run_status`, `wes_list_runs`, and `wes_cancel_run`
tools wrap the same endpoints and handle auth for you.

## Retrieving results

Outputs are written under `s3://${S3_BUCKET_NAME}/Project/{ProjectId}/`, where
`S3_BUCKET_NAME` is server-side configuration. Read the authoritative per-run
paths from the run log rather than constructing them:

```bash
curl -s -H "Authorization: Bearer $NGS360_TOKEN" \
  "$WES_URL/runs/$RUN_ID" | jq .outputs.output_mapping
```

`outputs` is nested — workflow outputs under `outputs.output_mapping`, log
locations under `outputs.log_urls`.

## Cancelling a batch

```bash
while read -r _ RUN_ID; do
  curl -s -X POST -H "Authorization: Bearer $NGS360_TOKEN" \
    "$WES_URL/runs/$RUN_ID/cancel" > /dev/null
done < run_ids.txt
```

This marks the runs `CANCELING` in the WES database only. It does **not** stop
the HealthOmics runs, which keep executing and keep billing — cancel them in
HealthOmics (`aws omics cancel-run --id <omics_run_id>`) to actually stop the
work. The `omics_run_id` is the `workflow_run_id` field on the run log.

## Troubleshooting

| Symptom                                    | Cause                                                                |
| ------------------------------------------ | -------------------------------------------------------------------- |
| Every run `SYSTEM_ERROR` immediately       | Workflow URL wrong (`omics:` prefix, bad alias/version), or no `AWSHealthOmics (us-east)` deployment. `system_logs` says which |
| `500` on every submit                      | Missing `ProjectId` tag                                              |
| `401` on every submit                      | Auth scheme doesn't match `AUTH_METHOD` — Bearer vs `-u`             |
| All runs stuck `QUEUED`                     | The Lambda function or the EventBridge callback path — see [aws_omics_usage.md](aws_omics_usage.md#troubleshooting) |
| Some samples `EXECUTOR_ERROR`, others fine | Per-sample inputs missing or unreadable by the HealthOmics role       |
| `/tasks` empty for every run               | Expected — `task_logs` is never populated. Use HealthOmics/CloudWatch |

## Related

- [GA4GH-WES-HealthOmics-Guide.md](GA4GH-WES-HealthOmics-Guide.md) — single-run guide, API reference
- [aws_omics_usage.md](aws_omics_usage.md) — AWS-side configuration and IAM
- [NGS360-Integration.md](NGS360-Integration.md) — cross-process contracts
- [PAML](https://github.com/NGS360/PAML/) — batch submission framework
