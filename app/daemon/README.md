# Workflow Submission Daemon

This daemon submits workflows from the GA4GH WES API to various workflow execution providers and monitors their status.

## Supported Providers

- **SevenBridges/Velsera**: Submit workflows to the SevenBridges/Velsera platform
- **AWS HealthOmics**: Submit workflows to AWS HealthOmics

## Configuration

The daemon is configured using environment variables:

### General Configuration

- `DATABASE_URI`: The URI for the database (required)
- `DAEMON_POLL_INTERVAL`: How often to poll for new workflows in seconds (default: 60)
- `DAEMON_STATUS_CHECK_INTERVAL`: How often to check workflow status in seconds (default: 300)
- `DAEMON_MAX_CONCURRENT_WORKFLOWS`: Maximum number of workflows to process concurrently (default: 10)

### SevenBridges/Velsera Configuration

- `SEVENBRIDGES_API_TOKEN`: API token for SevenBridges/Velsera (required for SevenBridges provider)
- `SEVENBRIDGES_API_ENDPOINT`: API endpoint URL for SevenBridges/Velsera (default: https://api.sbgenomics.com/v2)
- `SEVENBRIDGES_PROJECT`: Project ID for SevenBridges/Velsera (required for SevenBridges provider)

### AWS HealthOmics Configuration

- `AWS_ACCESS_KEY_ID`: AWS access key ID (required for AWS HealthOmics provider)
- `AWS_SECRET_ACCESS_KEY`: AWS secret access key (required for AWS HealthOmics provider)
- `AWS_REGION`: AWS region (default: us-east-1)
- `AWS_HEALTHOMICS_WORKFLOW_ROLE_ARN`: IAM role ARN for workflow execution (optional)
- `AWS_HEALTHOMICS_OUTPUT_URI`: S3 URI for workflow outputs (optional)

## Running the Daemon

### Command Line Options

```
usage: workflow_daemon.py [-h] [--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}] [--log-file LOG_FILE] [--db-uri DB_URI]
                         [--poll-interval POLL_INTERVAL] [--status-check-interval STATUS_CHECK_INTERVAL]
                         [--max-concurrent-workflows MAX_CONCURRENT_WORKFLOWS]

WES Workflow Submission Daemon

optional arguments:
  -h, --help            show this help message and exit
  --log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Set the logging level
  --log-file LOG_FILE   Log to this file in addition to stdout
  --db-uri DB_URI       Database URI (overrides environment variable)
  --poll-interval POLL_INTERVAL
                        How often to poll for new workflows (in seconds)
  --status-check-interval STATUS_CHECK_INTERVAL
                        How often to check workflow status (in seconds)
  --max-concurrent-workflows MAX_CONCURRENT_WORKFLOWS
                        Maximum number of workflows to process concurrently
```

### Example Usage

1. Set up environment variables:

```bash
# Database
export DATABASE_URI=postgresql://user:password@localhost/wes

# SevenBridges/Velsera
export SEVENBRIDGES_API_TOKEN=your-token
export SEVENBRIDGES_API_ENDPOINT=https://api.sbgenomics.com/v2
export SEVENBRIDGES_PROJECT=your-project-id

# AWS HealthOmics
export AWS_ACCESS_KEY_ID=your-access-key
export AWS_SECRET_ACCESS_KEY=your-secret-key
export AWS_REGION=us-east-1
export AWS_HEALTHOMICS_WORKFLOW_ROLE_ARN=arn:aws:iam::123456789012:role/workflow-role
export AWS_HEALTHOMICS_OUTPUT_URI=s3://your-bucket/outputs

# Daemon Configuration
export DAEMON_POLL_INTERVAL=60
export DAEMON_STATUS_CHECK_INTERVAL=300
export DAEMON_MAX_CONCURRENT_WORKFLOWS=10
```

2. Run the daemon:

```bash
python scripts/workflow_daemon.py --log-level INFO
```

## Specifying Provider Type

To specify which provider should execute a workflow, add a `provider_type` tag when submitting the workflow:

```json
{
  "workflow_params": { ... },
  "workflow_type": "CWL",
  "workflow_type_version": "v1.0",
  "workflow_url": "workflow.cwl",
  "tags": {
    "provider_type": "sevenbridges"  // or "healthomics"
  }
}
```

If no provider type is specified, the daemon will use the default provider (SevenBridges/Velsera).

## Running as a Service

For production use, it's recommended to run the daemon as a service using a process manager like systemd or Supervisor.

### Example systemd Service

Create a file at `/etc/systemd/system/wes-daemon.service`:

```ini
[Unit]
Description=WES Workflow Submission Daemon
After=network.target

[Service]
User=wes
Group=wes
WorkingDirectory=/path/to/GA4GH-WES-API-Service
EnvironmentFile=/path/to/GA4GH-WES-API-Service/.env
ExecStart=/path/to/GA4GH-WES-API-Service/scripts/workflow_daemon.py --log-level INFO --log-file /var/log/wes-daemon.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start the service:

```bash
sudo systemctl enable wes-daemon
sudo systemctl start wes-daemon
```

## Error Handling

The daemon logs errors but does not retry failed operations. If a workflow submission fails, the workflow will be marked as `SYSTEM_ERROR` and the error message will be stored in the workflow's tags.