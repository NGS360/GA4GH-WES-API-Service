"""Tests for AWS Omics executor."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.wes_service.daemon.executors.omics import OmicsExecutor
from src.wes_service.db.models import WorkflowRun, WorkflowState


@pytest.fixture
def mock_omics_client():
    """Create mock AWS Omics client."""
    with patch('boto3.client') as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.return_value = mock_client
        yield mock_client


@pytest.fixture
def omics_executor(mock_omics_client):
    """Create Omics executor with mocked client."""
    return OmicsExecutor(region_name="us-east-1")


@pytest.mark.asyncio
async def test_extract_workflow_id(omics_executor):
    """Test extracting workflow ID from different sources."""
    # From workflow_url with prefix
    run1 = WorkflowRun(workflow_url="omics:wf-12345")
    assert omics_executor._extract_workflow_id(run1) == "wf-12345"
    
    # From workflow_params
    run2 = WorkflowRun(
        workflow_url="https://example.com/workflow.wdl",
        workflow_params={"workflow_id": "wf-67890"}
    )
    assert omics_executor._extract_workflow_id(run2) == "wf-67890"
    
    # Direct from workflow_url
    run3 = WorkflowRun(workflow_url="wf-abcdef")
    assert omics_executor._extract_workflow_id(run3) == "wf-abcdef"


@pytest.mark.asyncio
async def test_convert_params_to_omics(omics_executor):
    """Test converting WES parameters to Omics format."""
    wes_params = {
        "workflow_id": "wf-12345",
        "input_file": "s3://bucket/input.fastq",
        "reference_genome": "s3://bucket/reference.fa",
        "threads": 4
    }
    
    omics_params = omics_executor._convert_params_to_omics(wes_params)
    
    # workflow_id should be excluded
    assert "workflow_id" not in omics_params
    
    # Other parameters should be included
    assert omics_params["input_file"] == "s3://bucket/input.fastq"
    assert omics_params["reference_genome"] == "s3://bucket/reference.fa"
    assert omics_params["threads"] == 4


@pytest.mark.asyncio
async def test_execute_workflow_success(omics_executor, mock_omics_client, test_db):
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
        workflow_url="omics:wf-12345",
        workflow_params={"input_file": "s3://bucket/input.fastq"},
        tags={},
    )
    test_db.add(run)
    await test_db.commit()
    
    # Execute workflow with sleep mocked
    with patch('asyncio.sleep', return_value=None):  # Skip sleep
        await omics_executor.execute(test_db, run)
    
    # Verify state updated
    await test_db.refresh(run)
    assert run.state == WorkflowState.COMPLETE
    assert run.exit_code == 0
    assert run.outputs == {"output_location": "s3://bucket/output/"}
    
    # Verify AWS calls
    mock_omics_client.start_run.assert_called_once()
    assert mock_omics_client.get_run.call_count == 3


@pytest.mark.asyncio
async def test_execute_workflow_failure(omics_executor, mock_omics_client, test_db):
    """Test failed workflow execution."""
    # Mock responses
    mock_omics_client.start_run.return_value = {"id": "omics-run-456"}
    
    # Mock get_run responses for status checks - failure case
    mock_omics_client.get_run.side_effect = [
        {"status": "PENDING"},
        {"status": "RUNNING"},
        {"status": "FAILED"}
    ]
    
    # Create test run
    run = WorkflowRun(
        id="test-run-456",
        state=WorkflowState.QUEUED,
        workflow_type="WDL",
        workflow_type_version="1.0",
        workflow_url="omics:wf-12345",
        workflow_params={"input_file": "s3://bucket/input.fastq"},
        tags={},
    )
    test_db.add(run)
    await test_db.commit()
    
    # Execute workflow with sleep mocked
    with patch('asyncio.sleep', return_value=None):  # Skip sleep
        await omics_executor.execute(test_db, run)
    
    # Verify state updated
    await test_db.refresh(run)
    assert run.state == WorkflowState.EXECUTOR_ERROR
    assert run.exit_code == 1
    
    # Verify AWS calls
    mock_omics_client.start_run.assert_called_once()
    assert mock_omics_client.get_run.call_count == 3