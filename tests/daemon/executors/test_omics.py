"""Tests for AWS Omics executor."""

import pytest
from unittest.mock import MagicMock, patch

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

    omics_params = omics_executor._convert_params_to_omics(wes_params, "WDL")

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

    # Mock get_run responses for status checks (3 for monitoring + 1 for _get_run_outputs)
    mock_omics_client.get_run.side_effect = [
        {"status": "PENDING"},
        {"status": "RUNNING"},
        {
            "status": "COMPLETED",
            "outputUri": "s3://bucket/output/",
            "logLocation": {
                "runLogStream": (
                    "arn:aws:logs:us-east-1:123456789012:log-group:"
                    "/aws/omics/WorkflowLog:log-stream:run/omics-run-123"
                )
            }
        },
        {
            "status": "COMPLETED",
            "outputUri": "s3://bucket/output/",
            "logLocation": {
                "runLogStream": (
                    "arn:aws:logs:us-east-1:123456789012:log-group:"
                    "/aws/omics/WorkflowLog:log-stream:run/omics-run-123"
                )
            }
        }
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
    assert "output_location" in run.outputs
    assert "logs" in run.outputs
    assert "run_log" in run.outputs["logs"]
    assert run.stdout_url == run.outputs["logs"]["run_log"]
    assert "https://us-east-1.console.aws.amazon.com/cloudwatch/home" in run.stdout_url

    # Verify AWS calls
    mock_omics_client.start_run.assert_called_once()
    assert mock_omics_client.get_run.call_count == 4


@pytest.mark.asyncio
async def test_execute_workflow_failure(omics_executor, mock_omics_client, test_db):
    """Test failed workflow execution."""
    # Mock responses
    mock_omics_client.start_run.return_value = {"id": "omics-run-456"}

    # Mock get_run responses for status checks - failure case (3 for monitoring + 1 for double-check)
    mock_omics_client.get_run.side_effect = [
        {"status": "PENDING"},
        {"status": "RUNNING"},
        {
            "status": "FAILED",
            "logLocation": {
                "runLogStream": (
                    "arn:aws:logs:us-east-1:123456789012:log-group:"
                    "/aws/omics/WorkflowLog:log-stream:run/omics-run-456"
                )
            }
        },
        {
            "status": "FAILED",
            "logLocation": {
                "runLogStream": (
                    "arn:aws:logs:us-east-1:123456789012:log-group:"
                    "/aws/omics/WorkflowLog:log-stream:run/omics-run-456"
                )
            }
        }
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
    assert mock_omics_client.get_run.call_count == 4


@pytest.mark.asyncio
async def test_get_run_outputs(omics_executor, mock_omics_client):
    """Test extracting outputs and logs from Omics run."""
    # Mock response with CloudWatch logs
    mock_omics_client.get_run.return_value = {
        "status": "COMPLETED",
        "outputUri": "s3://bucket/output/",
        "logLocation": {
            "runLogStream": (
                "arn:aws:logs:us-east-1:123456789012:log-group:/aws/omics/WorkflowLog:"
                "log-stream:run/test-run-789"
            )
        },
        "tasks": [
            {
                "name": "task1",
                "id": "task-123",
                "status": "COMPLETED"
            },
            {
                "name": "task2",
                "id": "task-456",
                "status": "COMPLETED"
            }
        ]
    }

    # Get outputs
    outputs = await omics_executor._get_run_outputs("test-run-789")

    # Verify output structure
    assert outputs["output_location"] == "s3://bucket/output/"
    assert "logs" in outputs
    assert "run_log" in outputs["logs"]
    assert "log_group" in outputs["logs"]
    assert "log_stream" in outputs["logs"]

    # Verify CloudWatch URL format
    assert "https://us-east-1.console.aws.amazon.com/cloudwatch/home" in outputs["logs"]["run_log"]
    assert "/aws/omics/WorkflowLog" in outputs["logs"]["log_group"]
    assert "run/test-run-789" in outputs["logs"]["log_stream"]

    # Verify task logs
    assert "task_logs" in outputs["logs"]
    assert "main" in outputs["logs"]["task_logs"]


@pytest.mark.asyncio
async def test_update_task_log_urls(omics_executor, test_db):
    """Test updating task log URLs in the database."""
    from src.wes_service.db.models import TaskLog

    # Create a test run
    run = WorkflowRun(
        id="test-run-task-logs",
        state=WorkflowState.COMPLETE,
        workflow_type="WDL",
        workflow_type_version="1.0",
        workflow_url="omics:wf-12345"
    )
    test_db.add(run)

    # Create test tasks
    task1 = TaskLog(
        id="task-1",
        run_id=run.id,
        name="task1"
    )
    task2 = TaskLog(
        id="task-2",
        run_id=run.id,
        name="task2"
    )
    test_db.add(task1)
    test_db.add(task2)
    await test_db.commit()

    # Mock task logs
    task_logs = {
        "task1": "https://example.com/logs/task1.log",
        "task2": "https://example.com/logs/task2.log"
    }

    # Update task log URLs
    await omics_executor._update_task_log_urls(test_db, run.id, task_logs)

    # Verify URLs were updated
    await test_db.refresh(task1)
    await test_db.refresh(task2)

    assert task1.stdout_url == "https://example.com/logs/task1.log"
