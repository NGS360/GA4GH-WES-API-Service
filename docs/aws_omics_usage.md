# Using AWS Omics with WES API

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
OMICS_OUTPUT_BUCKET=s3://your-output-bucket

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

You can also use the included Python client script to interact with the WES API:

```python
import sys
import json
from scripts.wes_client import WESClient

# Create WES client
client = WESClient(
    url="http://your-wes-server/ga4gh/wes/v1",
    username="your-username",
    password="your-password"
)

# Submit a workflow
run_id = client.submit_workflow(
    workflow_type="WDL",
    workflow_type_version="1.0",
    workflow_url="omics:wf-12345abcdef",
    workflow_params={
        "input_file": "s3://your-bucket/input.fastq",
        "reference_genome": "s3://your-bucket/reference.fa"
    }
)

print(f"Submitted workflow with run ID: {run_id}")

# Check status
status = client.get_run_status(run_id)
print(f"Status: {status}")
```

## AWS Omics-Specific Considerations

1. **Workflow IDs**: Ensure you're using the correct workflow ID from AWS Omics. You can find this in the AWS Omics console.

2. **IAM Permissions**: The role specified in `OMICS_ROLE_ARN` needs appropriate permissions to run workflows in AWS Omics and access your S3 buckets.

3. **Output Location**: Results will be stored in the S3 bucket specified in `OMICS_OUTPUT_BUCKET`, under a path that includes the WES run ID.

4. **Cost Management**: AWS Omics incurs costs based on compute usage. Monitor your AWS billing dashboard when running workflows.

5. **Logging**: AWS Omics stores logs in CloudWatch. For detailed troubleshooting, you may need to check both the WES API logs and AWS CloudWatch logs.