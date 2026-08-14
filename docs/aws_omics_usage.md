# Using AWS Omics with WES API

> [!WARNING]
> **This document is out of date and its examples will not work.**
>
> It describes the daemon-based Omics executor, which was removed in February
> 2026 (`b75bf00 remove daemon`). Three things in here are no longer true:
>
> - **`workflow_url=omics:<id>` / `healthomics:<id>`.** The prefix was handled by
>   the deleted executor. The server now reads `workflow_url` as
>   `NGS360WORKFLOWID[:ALIAS_OR_VERSION]` and resolves it against the NGS360
>   workflow catalog. A prefixed value is parsed as a workflow called `omics`
>   and fails to resolve — silently, because submission errors are logged rather
>   than returned, so the run is created and then never progresses.
> - **`WORKFLOW_EXECUTOR=omics`.** Still accepted by config, but read by nothing.
> - **Choosing an executor at submit time.** Where a run executes is now
>   determined by the deployment recorded against that workflow version in the
>   NGS360 catalog, not by anything in the request.
>
> To submit a run today, see the CLI documentation in
> [`packages/wes-client/README.md`](../packages/wes-client/README.md#cli).
> This document needs a rewrite by someone who knows the current catalog and
> Lambda submission flow.

This guide explains how to use the WES API to run workflows on AWS Omics.

## Prerequisites

1. AWS account with Omics access
2. IAM role with appropriate permissions
3. Workflows already imported into AWS Omics
4. Input data available in S3

## Configuration

Set the following environment variables in your `.env` file:

```bash
# AWS Omics Configuration
OMICS_REGION=us-east-1
OMICS_ROLE_ARN=arn:aws:iam::123456789012:role/OmicsWorkflowRole
S#_BUCKET_NAME=s3://your-output-bucket

# Set workflow executor to Omics
WORKFLOW_EXECUTOR=omics
```

Ensure the IAM role has permissions to:
- Run workflows in AWS Omics
- Read from your input S3 buckets
- Write to your output S3 bucket

## Running Specific Workflows

To run a workflow on AWS Omics using the WES API, you need:

1. The workflow ID from AWS Omics
2. Input file paths in S3
3. Any additional parameters required by your workflow

### Example: Running a Workflow

```bash
curl -X POST "http://your-wes-server/ga4gh/wes/v1/runs" \
  -u username:password \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=omics:wf-12345abcdef" \
  -F "workflow_params={\"input_file\": \"s3://your-bucket/input.fastq\", \"reference_genome\": \"s3://your-bucket/reference.fa\"}"
```

In this example:
- `workflow_url` uses the format `omics:workflow-id` where `workflow-id` is the ID of your workflow in AWS Omics
- `workflow_params` includes all the input parameters required by your workflow

### Running Multiple Workflows

To run multiple workflows, simply make multiple API calls with different parameters:

```bash
# First workflow
curl -X POST "http://your-wes-server/ga4gh/wes/v1/runs" \
  -u username:password \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=omics:wf-12345abcdef" \
  -F "workflow_params={\"input_file\": \"s3://your-bucket/sample1.fastq\"}"

# Second workflow
curl -X POST "http://your-wes-server/ga4gh/wes/v1/runs" \
  -u username:password \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=omics:wf-12345abcdef" \
  -F "workflow_params={\"input_file\": \"s3://your-bucket/sample2.fastq\"}"

# Third workflow
curl -X POST "http://your-wes-server/ga4gh/wes/v1/runs" \
  -u username:password \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=omics:wf-12345abcdef" \
  -F "workflow_params={\"input_file\": \"s3://your-bucket/sample3.fastq\"}"
```

## Monitoring Workflows

You can monitor the status of your workflows using the standard WES API endpoints:

```bash
# Get status
curl -X GET "http://your-wes-server/ga4gh/wes/v1/runs/{run_id}/status" \
  -u username:password

# Get detailed log
curl -X GET "http://your-wes-server/ga4gh/wes/v1/runs/{run_id}" \
  -u username:password

# List all runs
curl -X GET "http://your-wes-server/ga4gh/wes/v1/runs" \
  -u username:password
```

## Canceling Workflows

To cancel a running workflow:

```bash
curl -X POST "http://your-wes-server/ga4gh/wes/v1/runs/{run_id}/cancel" \
  -u username:password
```

## Using a Python Client

The `wes-client` package in this repo talks to the WES API. See
[`packages/wes-client/README.md`](../packages/wes-client/README.md).

```python
from wes_client import BasicAuth, WesClient

# The service root -- the client adds the /ga4gh/wes/v1 prefix itself.
with WesClient(
    "http://your-wes-server",
    auth=BasicAuth("your-username", "your-password"),
) as client:
    run = client.submit_run(
        workflow_type="WDL",
        workflow_type_version="1.0",
        # An NGS360 catalog workflow id, optionally ":version".
        # No prefix -- the catalog decides where the run executes.
        workflow_url="fcf1b62cf3b44b549afd51c0318fc087",
        workflow_params={
            "input_file": "s3://your-bucket/input.fastq",
            "reference_genome": "s3://your-bucket/reference.fa",
        },
        tags={"ProjectId": "P-123"},
    )
    print(f"Submitted workflow with run ID: {run.run_id}")

    status = client.get_run_status(run.run_id)
    print(f"Status: {status.state}")
```

Or from the shell, with the `cli` extra installed:

```bash
export WES_API_URL=http://your-wes-server
export WES_USERNAME=your-username WES_PASSWORD=your-password

wes runs submit --workflow-url fcf1b62cf3b44b549afd51c0318fc087 \
    --workflow-type WDL --workflow-type-version 1.0 \
    --param input_file=s3://your-bucket/input.fastq \
    --tag ProjectId=P-123
wes runs status <run_id>

# Submit one run per sample, then block until they all finish.
for f in s3://bucket/a.fastq s3://bucket/b.fastq; do
    wes runs submit --workflow-url fcf1b62cf3b44b549afd51c0318fc087 \
        --workflow-type WDL --workflow-type-version 1.0 \
        --param input_file="$f" --tag ProjectId=P-123
done
wes runs wait <run_id> <run_id>
```

## AWS Omics-Specific Considerations

1. **Workflow IDs**: Ensure you're using the correct workflow ID from AWS Omics. You can find this in the AWS Omics console.

2. **IAM Permissions**: The role specified in `OMICS_ROLE_ARN` needs appropriate permissions to run workflows in AWS Omics and access your S3 buckets.

3. **Output Location**: Results will be stored in the S3 bucket specified in `S3_BUCKET_NAME`, under a path that includes the WES run ID.

4. **Cost Management**: AWS Omics incurs costs based on compute usage. Monitor your AWS billing dashboard when running workflows.

5. **Logging**: AWS Omics stores logs in CloudWatch. For detailed troubleshooting, you may need to check both the WES API logs and AWS CloudWatch logs.
