# GA4GH WES API Service

This is an implementation of the [GA4GH Workflow Execution Service (WES) API](https://github.com/ga4gh/workflow-execution-service-schemas).

## Overview

The GA4GH WES API provides a standard way for users to submit workflow requests to workflow execution systems and to monitor their execution. This implementation allows you to submit workflows to different service providers:

- AWS HealthOmics
- Arvados
- SevenBridges/Velsera

## Setup

### Prerequisites

- Python 3.8+
- PostgreSQL database
- AWS account (for AWS HealthOmics)
- Arvados account (for Arvados)
- SevenBridges/Velsera account (for SevenBridges/Velsera)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/ga4gh-wes-api-service.git
   cd ga4gh-wes-api-service
   ```

2. Create a virtual environment and install dependencies:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   ```
   # Database configuration
   export DATABASE_URL=postgresql://username:password@localhost/wes_db
   
   # Default service provider
   export DEFAULT_SERVICE_PROVIDER=aws_omics
   
   # AWS HealthOmics configuration
   export AWS_OMICS_ROLE_ARN=arn:aws:iam::123456789012:role/omics-service-role
   export AWS_OMICS_OUTPUT_URI=s3://your-bucket/output
   
   # Arvados configuration
   export ARVADOS_API_URL=https://arvados.example.com/api
   export ARVADOS_API_TOKEN=your_arvados_token
   
   # SevenBridges/Velsera configuration
   export SEVENBRIDGES_API_URL=https://api.sbgenomics.com/v2
   export SEVENBRIDGES_API_TOKEN=your_sevenbridges_token
   export SEVENBRIDGES_PROJECT=your_project_id
   ```

4. Initialize the database:
   ```
   flask db upgrade
   ```

5. Run the application:
   ```
   flask run
   ```

## Usage

### API Endpoints

The service implements the standard GA4GH WES API endpoints:

- `GET /ga4gh/wes/v1/service-info` - Get service information
- `GET /ga4gh/wes/v1/runs` - List workflow runs
- `POST /ga4gh/wes/v1/runs` - Submit a new workflow run
- `GET /ga4gh/wes/v1/runs/{run_id}` - Get detailed information about a workflow run
- `GET /ga4gh/wes/v1/runs/{run_id}/status` - Get status of a workflow run
- `POST /ga4gh/wes/v1/runs/{run_id}/cancel` - Cancel a workflow run

### Submitting Workflows to Different Service Providers

When submitting a workflow, you can specify which service provider to use by including a `service_provider` field in your request:

```json
{
  "workflow_url": "https://example.com/workflow.wdl",
  "workflow_type": "WDL",
  "workflow_type_version": "1.0",
  "service_provider": "aws_omics",
  "workflow_params": {
    "input_file": "s3://my-bucket/input.txt",
    "output_dir": "s3://my-bucket/output/",
    "provider_params": {
      "roleArn": "arn:aws:iam::123456789012:role/custom-role",
      "outputUri": "s3://custom-bucket/output"
    }
  }
}
```

Available service providers:
- `aws_omics` - AWS HealthOmics
- `arvados` - Arvados
- `sevenbridges` - SevenBridges/Velsera

### Provider-Specific Parameters

Each service provider may require specific parameters. You can include these in the `provider_params` object within your `workflow_params`:

#### AWS HealthOmics

```json
"provider_params": {
  "roleArn": "arn:aws:iam::123456789012:role/custom-role",
  "outputUri": "s3://custom-bucket/output"
}
```

#### Arvados

```json
"provider_params": {
  "name": "My Workflow Run",
  "runtime_constraints": {
    "vcpus": 2,
    "ram": 4000000000
  }
}
```

#### SevenBridges/Velsera

```json
"provider_params": {
  "project": "my-project-id",
  "execution_settings": {
    "instance_type": "c4.2xlarge"
  }
}
```

## Web Interface

The service also provides a web interface for submitting and monitoring workflow runs:

- `/` - Home page
- `/runs` - List of workflow runs
- `/runs/new` - Submit a new workflow run
- `/runs/{run_id}` - View details of a workflow run

## Development

### Running Tests

```
pytest tests/
```

### Adding a New Service Provider

To add a new service provider:

1. Create a new provider class that implements the `WorkflowServiceProvider` interface
2. Add the provider to the `ServiceProviderFactory`
3. Update the documentation and web interface

## License

[MIT License](LICENSE)
