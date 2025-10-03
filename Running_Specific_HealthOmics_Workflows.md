# Running Specific Workflows in AWS Omics

This guide provides step-by-step instructions for running specific workflows in AWS Omics using the GA4GH WES API implementation.

## Prerequisites

1. AWS account with Omics access
2. Workflow(s) already imported into AWS Omics
3. Input data uploaded to S3
4. WES API service configured and running with Omics executor

## Setup

1. Configure the WES API service to use the Omics executor by setting in your `.env` file:

```bash
# Set executor to Omics
WORKFLOW_EXECUTOR=omics

# Configure AWS Omics settings
OMICS_REGION=us-east-1
OMICS_ROLE_ARN=arn:aws:iam::123456789012:role/OmicsWorkflowRole
OMICS_OUTPUT_BUCKET=s3://your-bucket/output-path
```

2. Ensure you have AWS credentials configured on the system running the WES API service

## Method 1: Using the API Directly

### Running a Single Workflow

```bash
curl -X POST "http://localhost:8000/ga4gh/wes/v1/runs" \
  -u username:password \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=omics:wf-12345abcdef" \
  -F "workflow_params={\"input_file\": \"s3://your-bucket/input.fastq\"}"
```

Replace `wf-12345abcdef` with your actual AWS Omics workflow ID.

### Running Multiple Workflows

For running multiple workflows with different input files, make multiple API calls:

```bash
# First workflow
curl -X POST "http://localhost:8000/ga4gh/wes/v1/runs" \
  -u username:password \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=omics:wf-12345abcdef" \
  -F "workflow_params={\"input_file\": \"s3://your-bucket/sample1.fastq\"}"

# Second workflow
curl -X POST "http://localhost:8000/ga4gh/wes/v1/runs" \
  -u username:password \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=omics:wf-12345abcdef" \
  -F "workflow_params={\"input_file\": \"s3://your-bucket/sample2.fastq\"}"

# Third workflow
curl -X POST "http://localhost:8000/ga4gh/wes/v1/runs" \
  -u username:password \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=omics:wf-12345abcdef" \
  -F "workflow_params={\"input_file\": \"s3://your-bucket/sample3.fastq\"}"
```

## Method 2: Using the Provided Script

We've included a convenience script for running multiple workflows with the same workflow ID but different input files.

```bash
python scripts/run_omics_workflows.py \
  --wes-url http://localhost:8000/ga4gh/wes/v1 \
  --username your_username \
  --password your_password \
  --workflow-id wf-12345abcdef \
  --workflow-type WDL \
  --workflow-version 1.0 \
  --input-files s3://your-bucket/sample1.fastq s3://your-bucket/sample2.fastq s3://your-bucket/sample3.fastq \
  --input-param-name input_file \
  --additional-params '{"reference_genome": "s3://your-bucket/reference.fa"}' \
  --monitor
```

This script will:
1. Submit all workflows in sequence
2. Provide run IDs for each submission
3. Monitor the workflows until completion if `--monitor` flag is used

### Script Options

```
--wes-url         WES API URL (default: http://localhost:8000/ga4gh/wes/v1)
--username        WES API username (can also use WES_USERNAME env var)
--password        WES API password (can also use WES_PASSWORD env var)
--workflow-id     AWS Omics workflow ID
--workflow-type   Workflow type (default: WDL)
--workflow-version  Workflow type version (default: 1.0)
--input-files     List of input file paths (space separated)
--input-param-name  Name of input parameter (default: input_file)
--additional-params Additional parameters as JSON string
--monitor         Monitor workflow execution
--poll-interval   Polling interval in seconds (default: 30)
```

## Monitoring Workflows

To monitor the status of submitted workflows:

```bash
# Get status of a specific run
curl -X GET "http://localhost:8000/ga4gh/wes/v1/runs/your-run-id/status" \
  -u username:password

# Get detailed log
curl -X GET "http://localhost:8000/ga4gh/wes/v1/runs/your-run-id" \
  -u username:password
```

## Example: Running 3 Samples through a Variant Calling Pipeline

```bash
python scripts/run_omics_workflows.py \
  --workflow-id wf-abcdef123456 \
  --input-files \
    s3://genomics-data/patient1.fastq \
    s3://genomics-data/patient2.fastq \
    s3://genomics-data/patient3.fastq \
  --additional-params '{
    "reference_genome": "s3://references/genome.fasta", 
    "threads": 8, 
    "min_quality": 20
  }' \
  --monitor
```

## Retrieving Results

Once workflows are complete, you can find the outputs at:
- S3 location: `{OMICS_OUTPUT_BUCKET}/runs/{run_id}/output/`
- Or through the detailed run log: `GET /runs/{run_id}`

## Troubleshooting

1. **Authentication errors**: Ensure your AWS credentials have permission to run Omics workflows
2. **Parameter errors**: Verify the workflow_id is correct and that input parameters match what the workflow expects
3. **Access errors**: Check that the role specified in `OMICS_ROLE_ARN` has access to read the input data and write to the output location
4. **Status errors**: If a workflow fails, check the detailed run log for error messages