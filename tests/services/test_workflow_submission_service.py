"""Tests for workflow submission service."""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock

from src.wes_service.db.models import WorkflowRun, WorkflowState
from src.wes_service.services.workflow_submission_service import (
    LambdaWorkflowSubmissionService,
    WorkflowSubmissionService,
)


@pytest.mark.asyncio
class TestWorkflowSubmissionService:
    """Tests for WorkflowSubmissionService."""

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.boto3.client')
    def test_init(self, mock_boto3_client, mock_get_settings):
        """Test service initialization."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        # Mock environment variables
        with patch.dict('os.environ', {
            'LAMBDA_REGION': 'us-west-2',
            'LAMBDA_FUNCTION_NAME': 'test-function'
        }):
            service = LambdaWorkflowSubmissionService()

        # Verify initialization
        assert service.ngs360_api_url == "https://test-ngs360.example.com"
        mock_boto3_client.assert_called_once_with('lambda', region_name='us-west-2')

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.requests.get')
    async def test_get_engine_id_from_ngs360_success(self, mock_requests_get, mock_get_settings):
        """Test successful NGS360 API call."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        # Mock requests response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"engine_id": "12345"}
        mock_requests_get.return_value = mock_response

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        # Test the method
        engine_id = await service._get_engine_id_from_ngs360("test-workflow-id")

        # Verify results
        assert engine_id == "12345"
        mock_requests_get.assert_called_once()

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.requests.get')
    async def test_get_engine_id_from_ngs360_api_error(self, mock_requests_get, mock_get_settings):
        """Test NGS360 API error handling."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        # Mock requests response with error
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"
        mock_requests_get.return_value = mock_response

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        # Test error handling
        with pytest.raises(Exception, match="NGS360 API returned status 404"):
            await service._get_engine_id_from_ngs360("nonexistent-workflow")

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.requests.get')
    async def test_get_engine_id_from_ngs360_missing_engine_id(self, mock_requests_get, mock_get_settings):
        """Test handling of missing engine_id in response."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        # Mock requests response without engine_id
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "Test Workflow", "engine": "AWSHealthOmics"}
        mock_requests_get.return_value = mock_response

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        # Test error handling
        with pytest.raises(Exception, match="engine_id not found for workflow"):
            await service._get_engine_id_from_ngs360("test-workflow-id")

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.boto3.client')
    @patch('src.wes_service.services.workflow_submission_service.requests.get')
    async def test_submit_workflow_success(self, mock_requests_get, mock_boto3_client, mock_get_settings):
        """Test successful workflow submission."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        # Mock NGS360 API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"engine_id": "67890"}
        mock_requests_get.return_value = mock_response

        # Mock Lambda client
        mock_lambda_client = MagicMock()
        mock_lambda_response = {
            'StatusCode': 200,
            'Payload': MagicMock()
        }
        mock_lambda_response['Payload'].read.return_value = json.dumps({
            'statusCode': 200,
            'omics_run_id': 'omics-12345'
        }).encode('utf-8')
        mock_lambda_client.invoke.return_value = mock_lambda_response
        mock_boto3_client.return_value = mock_lambda_client

        # Create test workflow run
        run = WorkflowRun(
            id="test-run-123",
            workflow_url="test-workflow-id",
            workflow_type="CWL",
            workflow_params={"input": "test"},
            tags={"project": "test"}
        )

        with patch.dict('os.environ', {'LAMBDA_FUNCTION_NAME': 'test-function'}):
            service = LambdaWorkflowSubmissionService()

        # Test workflow submission
        result = await service.submit_workflow(run)

        # Verify results
        assert result['omics_run_id'] == 'omics-12345'
        assert result['statusCode'] == 200

        # Verify Lambda was called with correct payload
        mock_lambda_client.invoke.assert_called_once()
        call_args = mock_lambda_client.invoke.call_args
        payload = json.loads(call_args[1]['Payload'])
        assert payload['workflow_id'] == '67890'  # Should use engine_id from NGS360
        assert payload['wes_run_id'] == 'test-run-123'

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.boto3.client')
    @patch('src.wes_service.services.workflow_submission_service.requests.get')
    async def test_submit_workflow_ngs360_failure(self, mock_requests_get, mock_boto3_client, mock_get_settings):
        """Test workflow submission when NGS360 API fails."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        # Mock NGS360 API error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_requests_get.return_value = mock_response

        # Create test workflow run
        run = WorkflowRun(
            id="test-run-123",
            workflow_url="test-workflow-id",
            workflow_type="CWL",
        )

        with patch.dict('os.environ', {'LAMBDA_FUNCTION_NAME': 'test-function'}):
            service = LambdaWorkflowSubmissionService()

        # Test error propagation
        with pytest.raises(Exception, match="NGS360 API returned status 500"):
            await service.submit_workflow(run)