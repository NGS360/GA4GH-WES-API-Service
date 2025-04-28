# Workflow Execution Service Architecture

This document describes the architecture and setup for the GA4GH WES API Service with separated workflow execution.

## Architecture Overview

The system is designed with a separation between the API service and the workflow execution:

1. **REST API Service**: Handles API requests, logs workflow requests to the database, and provides status updates
2. **Workflow Executor Service**: Monitors the database for new workflow requests and executes them using the appropriate WES provider

This separation provides several benefits:
- Decouples the API from workflow execution for better scalability
- Allows for asynchronous workflow processing
- Provides a consistent database record of all workflow requests and their status
- Makes the system more resilient to failures in the execution service
- Enables easier implementation of features like retries and parallel execution

## Setup Instructions

### 1. Apply Database Migrations

First, apply the database migrations to add the new tracking fields to the WorkflowRun model:

```bash
flask db upgrade
```

### 2. Start the Flask Application

Start the Flask application to serve the REST API:

```bash
python application.py
```

### 3. Start the Workflow Executor Service

In a separate terminal, start the workflow executor service:

```bash
./scripts/run_workflow_executor.py
```

You can configure the polling interval by setting the `WORKFLOW_POLL_INTERVAL` environment variable (default is 10 seconds):

```bash
WORKFLOW_POLL_INTERVAL=5 ./scripts/run_workflow_executor.py
```

## Usage

### Submitting a Workflow

Submit a workflow using the WES API:

```bash
curl -X POST \
  http://localhost:5000/api/ga4gh/wes/v1/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "workflow_params": {"outputUri": "s3://my-bucket/outputs/"},
    "workflow_type": "CWL",
    "workflow_type_version": "1.0",
    "workflow_url": "https://example.com/workflows/hello-world.cwl"
  }'
```

The API will log the request to the database and return a run ID. The workflow executor service will pick up the request and execute it.

### Checking Workflow Status

Check the status of a workflow:

```bash
curl http://localhost:5000/api/ga4gh/wes/v1/runs/{run_id}/status
```

### Getting Workflow Details

Get detailed information about a workflow:

```bash
curl http://localhost:5000/api/ga4gh/wes/v1/runs/{run_id}
```

### Cancelling a Workflow

Cancel a workflow:

```bash
curl -X POST http://localhost:5000/api/ga4gh/wes/v1/runs/{run_id}/cancel
```

## Running Tests

Run the integration tests:

```bash
python -m unittest tests/integration/test_workflow_execution.py
```

## Configuration

The system can be configured using environment variables:

- `DEFAULT_WES_PROVIDER`: The default WES provider to use (default: "Local")
- `WORKFLOW_POLL_INTERVAL`: The interval in seconds between database polls for the workflow executor (default: 10)
- `WES_API_URL`: The URL of the WES API for the client (default: "http://localhost:5000/api/ga4gh/wes/v1")

## Troubleshooting

### Workflow Stuck in QUEUED State

If a workflow is stuck in the QUEUED state, check that the workflow executor service is running and check its logs for errors.

### Workflow Failed with SYSTEM_ERROR

If a workflow fails with a SYSTEM_ERROR state, check the `error_message` field in the database for more information.

## Future Enhancements

1. Add support for more workflow types (Nextflow, Snakemake)
2. Implement additional WES providers (e.g., Cromwell, Toil)
3. Add more complex workflow examples
4. Create a mock WES provider for testing without external dependencies
5. Add performance testing for workflow execution
6. Implement a worker pool for parallel workflow execution
7. Add monitoring and alerting for failed workflows
8. Implement retry logic for failed workflows