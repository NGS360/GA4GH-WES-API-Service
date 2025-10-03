# AWS HealthOmics Integration Plan

This document outlines the implementation plan for adding AWS HealthOmics support to the GA4GH WES API Service.

## 1. Create HealthOmics Executor

Create a new file: `src/wes_service/daemon/executors/healthomics.py`

```python
"""AWS HealthOmics workflow executor implementation."""

import boto3
from datetime import datetime
import asyncio
import logging
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.wes_service.daemon.executors.base import WorkflowExecutor
from src.wes_service.db.models import TaskLog, WorkflowRun, WorkflowState

logger = logging.getLogger(__name__)

class HealthOmicsExecutor(WorkflowExecutor):
    """Executor for AWS HealthOmics workflows."""
    
    def __init__(self, region_name="us-east-1"):
        """Initialize with AWS region."""
        self.omics_client = boto3.client('omics', region_name=region_name)
    
    async def execute(self, db: AsyncSession, run: WorkflowRun) -> None:
        """Execute a workflow run on AWS HealthOmics."""
        try:
            # Update state to RUNNING
            run.state = WorkflowState.RUNNING
            run.start_time = datetime.utcnow()
            run.system_logs.append(f"Started execution at {run.start_time.isoformat()}")
            await db.commit()
            
            # Extract workflow ID from workflow_url or params
            workflow_id = self._extract_workflow_id(run)
            
            # Extract input file paths
            input_params = run.workflow_params or {}
            
            # Convert WES parameters to HealthOmics format
            omics_params = self._convert_params_to_healthomics(input_params)
            
            # Start the HealthOmics workflow run
            response = self.omics_client.start_run(
                workflowId=workflow_id,
                roleArn='arn:aws:iam::123456789012:role/OmicsWorkflowRole',  # Configure as needed
                parameters=omics_params,
                outputUri=f"s3://your-bucket/runs/{run.id}/output/",  # Configure as needed
                name=f"wes-run-{run.id}"
            )
            
            # Store the HealthOmics run ID
            omics_run_id = response['id']
            run.system_logs.append(f"Started AWS HealthOmics run: {omics_run_id}")
            await db.commit()
            
            # Monitor the run until completion
            final_state = await self._monitor_healthomics_run(db, run, omics_run_id)
            
            # Update run state based on HealthOmics result
            run.state = final_state
            run.end_time = datetime.utcnow()
            if final_state == WorkflowState.COMPLETE:
                run.exit_code = 0
                # Get outputs from HealthOmics
                outputs = self._get_run_outputs(omics_run_id)
                run.outputs = outputs
            else:
                run.exit_code = 1
            
            await db.commit()
            
        except Exception as e:
            logger.error(f"Error executing HealthOmics run {run.id}: {e}")
            # Handle errors
            run.state = WorkflowState.SYSTEM_ERROR
            run.end_time = datetime.utcnow()
            run.system_logs.append(f"Execution error: {str(e)}")
            run.exit_code = 1
            await db.commit()
            raise
    
    def _extract_workflow_id(self, run: WorkflowRun) -> str:
        """Extract HealthOmics workflow ID from run parameters."""
        # Option 1: Extract from workflow_url if it contains the ID
        if run.workflow_url and run.workflow_url.startswith("healthomics:"):
            return run.workflow_url.split(":")[-1]
        
        # Option 2: Look for workflow_id in parameters
        if run.workflow_params and "workflow_id" in run.workflow_params:
            return run.workflow_params["workflow_id"]
        
        # Option 3: Use the workflow_url directly if it looks like an ID
        return run.workflow_url
    
    def _convert_params_to_healthomics(self, wes_params: Dict[str, Any]) -> Dict[str, Any]:
        """Convert WES parameters to HealthOmics format."""
        omics_params = {}
        
        # Map input file paths to HealthOmics parameter format
        for key, value in wes_params.items():
            if key != "workflow_id":  # Skip the workflow_id if present
                if isinstance(value, str) and (value.startswith("s3://") or value.startswith("/")):
                    # This is likely a file path
                    omics_params[key] = value
                else:
                    # Other parameters
                    omics_params[key] = value
        
        return omics_params
    
    async def _monitor_healthomics_run(self, db: AsyncSession, run: WorkflowRun, omics_run_id: str) -> WorkflowState:
        """Monitor HealthOmics run until completion."""
        while True:
            # Get run status from HealthOmics
            response = self.omics_client.get_run(id=omics_run_id)
            status = response['status']
            
            # Log status update
            run.system_logs.append(f"HealthOmics status update: {status}")
            await db.commit()
            
            # Update task logs if available
            if 'tasks' in response:
                await self._update_task_logs(db, run, response['tasks'])
            
            # Map HealthOmics status to WES status
            if status == 'COMPLETED':
                return WorkflowState.COMPLETE
            elif status in ['FAILED', 'CANCELLED']:
                return WorkflowState.EXECUTOR_ERROR if status == 'FAILED' else WorkflowState.CANCELED
            elif status in ['STARTING', 'RUNNING', 'PENDING']:
                # Still running, wait and check again
                await asyncio.sleep(30)  # Check every 30 seconds
            else:
                # Unknown status
                run.system_logs.append(f"Unknown HealthOmics status: {status}")
                return WorkflowState.SYSTEM_ERROR
    
    async def _update_task_logs(self, db: AsyncSession, run: WorkflowRun, tasks: list) -> None:
        """Update task logs from HealthOmics tasks."""
        for task_data in tasks:
            # Check if task already exists
            task_id = f"omics-{task_data['id']}"
            
            # Create or update task log
            task = TaskLog(
                id=task_id,
                run_id=run.id,
                name=task_data.get('name', 'Unknown task'),
                cmd=[],  # HealthOmics doesn't expose the command
                start_time=datetime.fromisoformat(task_data.get('startTime', '').replace('Z', '+00:00')) if 'startTime' in task_data else None,
                end_time=datetime.fromisoformat(task_data.get('stopTime', '').replace('Z', '+00:00')) if 'stopTime' in task_data else None,
                exit_code=0 if task_data.get('status') == 'COMPLETED' else 1,
                system_logs=[f"HealthOmics task status: {task_data.get('status')}"]
            )
            
            db.add(task)
        
        await db.commit()
    
    def _get_run_outputs(self, omics_run_id: str) -> Dict[str, Any]:
        """Get outputs from completed HealthOmics run."""
        try:
            response = self.omics_client.get_run(id=omics_run_id)
            
            # Extract output information
            outputs = {}
            if 'outputUri' in response:
                outputs['output_location'] = response['outputUri']
            
            # Add any other output information available
            
            return outputs
        except Exception as e:
            logger.error(f"Error getting outputs for HealthOmics run {omics_run_id}: {e}")
            return {"error": str(e)}
```

## 2. Update Configuration Settings

Modify `src/wes_service/config.py` to add HealthOmics-specific settings:

```python
# Add to the Settings class
class Settings(BaseSettings):
    # ... existing settings ...
    
    # AWS HealthOmics Configuration
    healthomics_region: str = Field(
        default="us-east-1",
        description="AWS region for HealthOmics",
    )
    healthomics_role_arn: str = Field(
        default="",
        description="IAM role ARN for HealthOmics workflow execution",
    )
    healthomics_output_bucket: str = Field(
        default="",
        description="S3 bucket for HealthOmics workflow outputs",
    )
```

## 3. Modify Workflow Monitor

Update `src/wes_service/daemon/workflow_monitor.py` to use the HealthOmics executor:

```python
# Import the new executor
from src.wes_service.daemon.executors.healthomics import HealthOmicsExecutor
from src.wes_service.daemon.executors.local import LocalExecutor

class WorkflowMonitor:
    """Daemon that monitors and executes workflow runs."""

    def __init__(self):
        """Initialize workflow monitor."""
        self.settings = get_settings()
        
        # Choose executor based on configuration
        executor_type = self.settings.workflow_executor  # Add this setting
        if executor_type == "healthomics":
            self.executor = HealthOmicsExecutor(region_name=self.settings.healthomics_region)
        else:
            # Default to local executor
            self.executor = LocalExecutor()
            
        self.running = False
        self.active_runs: set[str] = set()
```

## 4. Add Example Usage Documentation

Create a new file: `docs/aws_healthomics_usage.md`

```markdown
# Using AWS HealthOmics with WES API

This guide explains how to use the WES API to run workflows on AWS HealthOmics.

## Prerequisites

1. AWS account with HealthOmics access
2. IAM role with appropriate permissions
3. Workflows already imported into HealthOmics
4. Input data available in S3

## Configuration

Set the following environment variables:

```bash
# AWS HealthOmics Configuration
HEALTHOMICS_REGION=us-east-1
HEALTHOMICS_ROLE_ARN=arn:aws:iam::123456789012:role/OmicsWorkflowRole
HEALTHOMICS_OUTPUT_BUCKET=your-output-bucket

# Set workflow executor to HealthOmics
WORKFLOW_EXECUTOR=healthomics
```

## Running Workflows

To run a workflow on AWS HealthOmics:

```bash
curl -X POST "http://your-wes-server/ga4gh/wes/v1/runs" \
  -u username:password \
  -F "workflow_type=WDL" \
  -F "workflow_type_version=1.0" \
  -F "workflow_url=healthomics:your-workflow-id" \
  -F "workflow_params={\"input_file\": \"s3://your-bucket/input.fastq\", \"reference_genome\": \"s3://your-bucket/reference.fa\"}"
```

The `workflow_url` should be in the format `healthomics:workflow-id` where `workflow-id` is the ID of your workflow in AWS HealthOmics.

## Monitoring Workflows

You can monitor the status of your workflow using the standard WES API endpoints:

```bash
# Get status
curl -X GET "http://your-wes-server/ga4gh/wes/v1/runs/{run_id}/status" \
  -u username:password

# Get detailed log
curl -X GET "http://your-wes-server/ga4gh/wes/v1/runs/{run_id}" \
  -u username:password
```

## Canceling Workflows

To cancel a running workflow:

```bash
curl -X POST "http://your-wes-server/ga4gh/wes/v1/runs/{run_id}/cancel" \
  -u username:password
```
```

## 5. Add Tests

Create a new file: `tests/daemon/executors/test_healthomics.py`

```python
"""Tests for AWS HealthOmics executor."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.wes_service.daemon.executors.healthomics import HealthOmicsExecutor
from src.wes_service.db.models import WorkflowRun, WorkflowState

@pytest.fixture
def mock_omics_client():
    """Create mock AWS HealthOmics client."""
    with patch('boto3.client') as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client
        yield mock_client

@pytest.fixture
def healthomics_executor(mock_omics_client):
    """Create HealthOmics executor with mocked client."""
    return HealthOmicsExecutor(region_name="us-east-1")

@pytest.mark.asyncio
async def test_extract_workflow_id(healthomics_executor):
    """Test extracting workflow ID from different sources."""
    # From workflow_url with prefix
    run1 = WorkflowRun(workflow_url="healthomics:wf-12345")
    assert healthomics_executor._extract_workflow_id(run1) == "wf-12345"
    
    # From workflow_params
    run2 = WorkflowRun(
        workflow_url="https://example.com/workflow.wdl",
        workflow_params={"workflow_id": "wf-67890"}
    )
    assert healthomics_executor._extract_workflow_id(run2) == "wf-67890"
    
    # Direct from workflow_url
    run3 = WorkflowRun(workflow_url="wf-abcdef")
    assert healthomics_executor._extract_workflow_id(run3) == "wf-abcdef"

@pytest.mark.asyncio
async def test_convert_params_to_healthomics(healthomics_executor):
    """Test converting WES parameters to HealthOmics format."""
    wes_params = {
        "workflow_id": "wf-12345",
        "input_file": "s3://bucket/input.fastq",
        "reference_genome": "s3://bucket/reference.fa",
        "threads": 4
    }
    
    omics_params = healthomics_executor._convert_params_to_healthomics(wes_params)
    
    # workflow_id should be excluded
    assert "workflow_id" not in omics_params
    
    # Other parameters should be included
    assert omics_params["input_file"] == "s3://bucket/input.fastq"
    assert omics_params["reference_genome"] == "s3://bucket/reference.fa"
    assert omics_params["threads"] == 4

@pytest.mark.asyncio
async def test_execute_workflow_success(healthomics_executor, mock_omics_client, test_db):
    """Test successful workflow execution."""
    # Mock responses
    mock_omics_client.start_run.return_value = {"id": "omics-run-123"}
    
    # Mock get_run responses for status checks
    mock_omics_client.get_run.side_effect = [
        {"status": "PENDING"},
        {"status": "RUNNING"},
        {"status": "COMPLETED", "outputUri": "s3://bucket/output/"}
    ]
    
    # Create test run
    run = WorkflowRun(
        id="test-run-123",
        state=WorkflowState.QUEUED,
        workflow_type="WDL",
        workflow_type_version="1.0",
        workflow_url="healthomics:wf-12345",
        workflow_params={"input_file": "s3://bucket/input.fastq"},
        tags={},
    )
    test_db.add(run)
    await test_db.commit()
    
    # Execute workflow
    with patch('asyncio.sleep', return_value=None):  # Skip sleep
        await healthomics_executor.execute(test_db, run)
    
    # Verify state updated
    await test_db.refresh(run)
    assert run.state == WorkflowState.COMPLETE
    assert run.exit_code == 0
    assert run.outputs == {"output_location": "s3://bucket/output/"}
    
    # Verify AWS calls
    mock_omics_client.start_run.assert_called_once()
    assert mock_omics_client.get_run.call_count == 3
```

## 6. Update Documentation

Update `README.md` to mention AWS HealthOmics support:

```markdown
## Workflow Engines

The current implementation includes:
- A stub local executor for demonstration
- AWS HealthOmics integration for running workflows on AWS HealthOmics

To integrate other workflow engines:

1. **Create a new executor** in `src/wes_service/daemon/executors/`
2. **Implement the `WorkflowExecutor` interface**
3. **Configure the daemon** to use your executor

Example executors:
- `LocalExecutor` - Stub implementation for demonstration
- `HealthOmicsExecutor` - For AWS HealthOmics workflows
- `CWLToolExecutor` - For Common Workflow Language (to be implemented)
- `CromwellExecutor` - For WDL workflows (to be implemented)
- `NextflowExecutor` - For Nextflow pipelines (to be implemented)
```

## 7. Update Requirements

Add AWS SDK to `pyproject.toml`:

```toml
[project]
# ...
dependencies = [
    # ... existing dependencies ...
    "boto3>=1.28.0",
]
```

## Implementation Steps

1. Create the HealthOmics executor file
2. Update configuration settings
3. Modify the workflow monitor
4. Add example usage documentation
5. Add tests for the HealthOmics executor
6. Update the README
7. Update dependencies

After implementing these changes, you'll be able to run workflows on AWS HealthOmics through the GA4GH WES API.