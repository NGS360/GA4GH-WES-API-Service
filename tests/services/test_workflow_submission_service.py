"""Tests for workflow submission service."""

import pytest
import json
from unittest.mock import patch, MagicMock

from src.wes_service.db.models import WorkflowRun, WorkflowState
from src.wes_service.services.workflow_submission_service import (
    LambdaWorkflowSubmissionService,
)

HTTPX_CLIENT_PATCH = (
    'src.wes_service.services.workflow_submission_service.httpx.AsyncClient'
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
    async def test_get_engine_id_from_ngs360_latest_version(self, mock_get_settings):
        """Test getting engine ID when no version specified."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "aliases": [],
            "versions": [
                {
                    "id": "version-1-id",
                    "version": 1,
                    "deployments": [
                        {
                            "id": "deployment-1-id",
                            "engine": "AWSHealthOmics (us-east)",
                            "external_id": "arn:aws:omics:us-east-1:123:workflow/456/version/v1",
                            "created_at": "2026-01-01T10:00:00"
                        }
                    ]
                },
                {
                    "id": "version-2-id",
                    "version": 2,
                    "deployments": [
                        {
                            "id": "deployment-2-id",
                            "engine": "AWSHealthOmics (us-east)",
                            "external_id": "arn:aws:omics:us-east-1:123:workflow/456/version/v2",
                            "created_at": "2026-01-02T10:00:00"
                        }
                    ]
                }
            ]
        }

        # Mock httpx.AsyncClient context manager
        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Make the get method async by creating an async mock
            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            # Test the method
            engine_id = await service._get_engine_id_from_ngs360("test-workflow-id")

        # Verify results
        assert engine_id == "arn:aws:omics:us-east-1:123:workflow/456/version/v2"

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    async def test_get_engine_id_from_ngs360_specific_version(self, mock_get_settings):
        """Test getting engine ID from specific version."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        # Mock httpx response with new structure
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "aliases": [],
            "versions": [
                {
                    "id": "version-1-id",
                    "version": 1,
                    "deployments": [
                        {
                            "id": "deployment-1-id",
                            "engine": "AWSHealthOmics (us-east)",
                            "external_id": "arn:aws:omics:us-east-1:123:workflow/456/version/v1",
                            "created_at": "2026-01-01T10:00:00"
                        }
                    ]
                },
                {
                    "id": "version-2-id",
                    "version": 2,
                    "deployments": [
                        {
                            "id": "deployment-2-id",
                            "engine": "AWSHealthOmics (us-east)",
                            "external_id": "arn:aws:omics:us-east-1:123:workflow/456/version/v2",
                            "created_at": "2026-01-02T10:00:00"
                        }
                    ]
                }
            ]
        }

        # Mock httpx.AsyncClient context manager
        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Make the get method async by creating an async mock
            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            # Test the method with specific version
            engine_id = await service._get_engine_id_from_ngs360("test-workflow-id:1")

        # Verify results - should return engine_id from version 1
        assert engine_id == "arn:aws:omics:us-east-1:123:workflow/456/version/v1"

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    async def test_get_engine_id_from_ngs360_with_alias(self, mock_get_settings):
        """Test getting engine ID using alias."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        # Mock httpx response with alias
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "aliases": [
                {
                    "alias": "production",
                    "version": 2
                }
            ],
            "versions": [
                {
                    "id": "version-1-id",
                    "version": 1,
                    "deployments": [
                        {
                            "id": "deployment-1-id",
                            "engine": "AWSHealthOmics (us-east)",
                            "external_id": "arn:aws:omics:us-east-1:123:workflow/456/version/v1",
                            "created_at": "2026-01-01T10:00:00"
                        }
                    ]
                },
                {
                    "id": "version-2-id",
                    "version": 2,
                    "deployments": [
                        {
                            "id": "deployment-2-id",
                            "engine": "AWSHealthOmics (us-east)",
                            "external_id": "arn:aws:omics:us-east-1:123:workflow/456/version/v2",
                            "created_at": "2026-01-02T10:00:00"
                        }
                    ]
                }
            ]
        }

        # Mock httpx.AsyncClient context manager
        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Make the get method async by creating an async mock
            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            # Test the method with alias
            engine_id = await service._get_engine_id_from_ngs360("test-workflow-id:production")

        # Verify results - should return engine_id from version 2 (aliased as production)
        assert engine_id == "arn:aws:omics:us-east-1:123:workflow/456/version/v2"

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    async def test_get_engine_id_from_ngs360_api_error(self, mock_get_settings):
        """Test NGS360 API error handling."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        # Mock httpx response with error
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        # Mock httpx.AsyncClient context manager
        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Make the get method async by creating an async mock
            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            # Test error handling
            with pytest.raises(Exception, match="NGS360 API returned status 404"):
                await service._get_engine_id_from_ngs360("nonexistent-workflow")

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    async def test_get_engine_id_from_ngs360_no_versions(self, mock_get_settings):
        """Test handling when no versions exist."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        # Mock httpx response with no versions
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "aliases": [],
            "versions": []
        }

        # Mock httpx.AsyncClient context manager
        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Make the get method async by creating an async mock
            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            # Test error handling
            with pytest.raises(RuntimeError, match="No versions found for workflow"):
                await service._get_engine_id_from_ngs360("test-workflow-id")

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    async def test_get_engine_id_from_ngs360_no_deployments(self, mock_get_settings):
        """Test handling when version has no AWSHealthOmics deployments."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        # Mock httpx response with version but no omics deployments
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "aliases": [],
            "versions": [
                {
                    "id": "version-1-id",
                    "version": 1,
                    "deployments": [
                        {
                            "id": "deployment-other-id",
                            "engine": "OtherEngine",
                            "external_id": "other-123",
                            "created_at": "2026-01-01T10:00:00"
                        }
                    ]
                }
            ]
        }

        # Mock httpx.AsyncClient context manager
        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Make the get method async by creating an async mock
            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            # Test error handling
            with pytest.raises(RuntimeError, match="has no deployments in AWSHealthOmics"):
                await service._get_engine_id_from_ngs360("test-workflow-id")

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.boto3.client')
    async def test_submit_workflow_success(self, mock_boto3_client, mock_get_settings):
        """Test successful workflow submission."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_settings.client_origin = "https://test-client.example.com"
        mock_settings.api_prefix = "/ga4gh/wes/v1"
        mock_get_settings.return_value = mock_settings

        # Mock NGS360 API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "aliases": [],
            "versions": [
                {
                    "id": "version-1-id",
                    "version": 1,
                    "deployments": [
                        {
                            "id": "deployment-submit-id",
                            "engine": "AWSHealthOmics (us-east)",
                            "external_id": "arn:aws:omics:us-east-1:123:workflow/456",
                            "created_at": "2026-01-01T10:00:00"
                        }
                    ]
                }
            ]
        }

        # Mock Lambda client
        mock_lambda_client = MagicMock()
        mock_lambda_response = {
            'StatusCode': 202,
        }
        mock_lambda_client.invoke.return_value = mock_lambda_response
        mock_boto3_client.return_value = mock_lambda_client

        # Create test workflow run
        run = WorkflowRun(
            id="test-run-123",
            workflow_url="test-workflow-id",
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_params={"input": "test"},
            tags={"project": "test"},
            project="test",
            task_name="test-task",
            system_logs=[],
        )

        with patch.dict('os.environ', {'LAMBDA_FUNCTION_NAME': 'test-function'}):
            service = LambdaWorkflowSubmissionService()

        # Mock httpx.AsyncClient context manager to prevent HTTP calls
        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Make the get method async by creating an async mock
            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            # Mock database session
            from unittest.mock import AsyncMock
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()

            # Test workflow submission (Event invocation is fire-and-forget)
            result = await service.submit_workflow(run, mock_db)

        # Event invocation is fire-and-forget, so submit_workflow returns None
        assert result is None

        # Verify Lambda was called with correct payload
        mock_lambda_client.invoke.assert_called_once()
        call_args = mock_lambda_client.invoke.call_args
        payload = json.loads(call_args[1]['Payload'])
        assert payload['workflow_id'] == 'arn:aws:omics:us-east-1:123:workflow/456'
        assert payload['wes_run_id'] == 'test-run-123'
        assert payload['tags']['callback_url'] == (
            "https://test-client.example.com/ga4gh/wes/v1/internal/callbacks/omics-state-change"
        )
        assert payload['tags']['WESRunId'] == 'test-run-123'
        assert payload['tags']['project'] == 'test'

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.boto3.client')
    async def test_submit_workflow_ngs360_failure(self, mock_boto3_client, mock_get_settings):
        """Test workflow submission when NGS360 API fails."""
        # Mock settings
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        # Mock NGS360 API error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        # Create test workflow run
        run = WorkflowRun(
            id="test-run-123",
            workflow_url="test-workflow-id",
            workflow_type="CWL",
            workflow_type_version="v1.0",
            tags={},
            project="test-project",
            task_name="test-task",
            system_logs=[],
        )

        with patch.dict('os.environ', {'LAMBDA_FUNCTION_NAME': 'test-function'}):
            service = LambdaWorkflowSubmissionService()

        # Mock httpx.AsyncClient context manager to prevent HTTP calls
        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            # Make the get method async by creating an async mock
            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            # Mock database session
            from unittest.mock import AsyncMock
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()

            # Service should catch the error and mark the run as SYSTEM_ERROR
            # with the failure recorded in system_logs, then commit.
            await service.submit_workflow(run, mock_db)

        assert run.state == WorkflowState.SYSTEM_ERROR
        assert len(run.system_logs) == 1
        assert "Failed to retrieve engine_id from NGS360 API" in run.system_logs[0]
        mock_db.commit.assert_awaited_once()

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    async def test_get_s3_uri_from_ngs360_success(self, mock_get_settings):
        """Resolve ngs360://<file-id> -> s3://... via NGS360 API."""
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "befcae0a-94f4-4807-afe3-d77b313e9c4f",
            "uri": "s3://bmsrd-ngs-omics/ngs360-file-store/staging/x.txt",
            "filename": "x.txt",
        }

        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            uri = await service._get_s3_uri_from_ngs360(
                "befcae0a-94f4-4807-afe3-d77b313e9c4f"
            )

        assert uri == "s3://bmsrd-ngs-omics/ngs360-file-store/staging/x.txt"

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    async def test_get_s3_uri_from_ngs360_not_found(self, mock_get_settings):
        """NGS360 file lookup 404 raises RuntimeError."""
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="NGS360 API returned status 404"):
                await service._get_s3_uri_from_ngs360("missing-file-id")

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    async def test_get_s3_uri_from_ngs360_non_s3_backed(self, mock_get_settings):
        """Non-s3 backed file raises RuntimeError."""
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "abc",
            "uri": "file:///tmp/local.txt",
        }

        with patch(HTTPX_CLIENT_PATCH) as mock_client_class:
            mock_client = MagicMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None

            async def mock_get(*args, **kwargs):
                return mock_response
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            with pytest.raises(RuntimeError, match="not backed by S3"):
                await service._get_s3_uri_from_ngs360("abc")

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    async def test_resolve_file_ids_in_params_nested(self, mock_get_settings):
        """Nested ngs360:// values inside workflow_params are all resolved,
        non-ngs360 values pass through, and duplicate ids are fetched once."""
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        with patch.dict('os.environ', {}):
            service = LambdaWorkflowSubmissionService()

        calls = []

        async def fake_get_s3_uri(file_id):
            calls.append(file_id)
            return f"s3://bucket/{file_id}.txt"

        with patch.object(
            service, "_get_s3_uri_from_ngs360", side_effect=fake_get_s3_uri
        ):
            params = {
                "sample_sheet": "ngs360://id-1",
                "reads": [
                    {"class": "File", "location": "ngs360://id-2"},
                    {"class": "File", "location": "ngs360://id-1"},
                ],
                "ref": "s3://bucket/ref.fa",
                "threads": 4,
            }
            resolved = await service._resolve_file_ids_in_params(params)

        assert resolved == {
            "sample_sheet": "s3://bucket/id-1.txt",
            "reads": [
                {"class": "File", "location": "s3://bucket/id-2.txt"},
                {"class": "File", "location": "s3://bucket/id-1.txt"},
            ],
            "ref": "s3://bucket/ref.fa",
            "threads": 4,
        }
        # id-1 appears twice but should only be fetched once due to caching
        assert sorted(calls) == ["id-1", "id-2"]

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.boto3.client')
    async def test_submit_workflow_resolves_file_ids(
        self, mock_boto3_client, mock_get_settings
    ):
        """submit_workflow rewrites ngs360:// values before invoking Lambda."""
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_settings.client_origin = "https://test-client.example.com"
        mock_settings.api_prefix = "/ga4gh/wes/v1"
        mock_get_settings.return_value = mock_settings

        mock_lambda_client = MagicMock()
        mock_lambda_client.invoke.return_value = {'StatusCode': 202}
        mock_boto3_client.return_value = mock_lambda_client

        run = WorkflowRun(
            id="run-file-resolve",
            workflow_url="test-workflow-id",
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_params={
                "sample_sheet": "ngs360://befcae0a-94f4-4807-afe3-d77b313e9c4f",
                "threads": 4,
            },
            tags={"project": "test"},
            project="test",
            task_name="test-task",
            system_logs=[],
        )

        with patch.dict('os.environ', {'LAMBDA_FUNCTION_NAME': 'test-function'}):
            service = LambdaWorkflowSubmissionService()

        with patch.object(
            service,
            "_get_engine_id_from_ngs360",
            return_value="arn:aws:omics:us-east-1:123:workflow/456",
        ), patch.object(
            service,
            "_get_s3_uri_from_ngs360",
            return_value="s3://bucket/sample_sheet.txt",
        ):
            from unittest.mock import AsyncMock
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()

            await service.submit_workflow(run, mock_db)

        # Original workflow_params on the run are preserved (audit trail)
        assert run.workflow_params["sample_sheet"] == (
            "ngs360://befcae0a-94f4-4807-afe3-d77b313e9c4f"
        )
        assert run.workflow_params["threads"] == 4

        # Lambda payload carries the resolved parameters
        mock_lambda_client.invoke.assert_called_once()
        payload = json.loads(mock_lambda_client.invoke.call_args[1]['Payload'])
        assert payload['parameters']['sample_sheet'] == "s3://bucket/sample_sheet.txt"
        assert payload['parameters']['threads'] == 4

    @patch('src.wes_service.services.workflow_submission_service.get_settings')
    @patch('src.wes_service.services.workflow_submission_service.boto3.client')
    async def test_submit_workflow_file_resolution_failure(
        self, mock_boto3_client, mock_get_settings
    ):
        """If file resolution fails, run is marked SYSTEM_ERROR and Lambda not invoked."""
        mock_settings = MagicMock()
        mock_settings.ngs360_api_url = "https://test-ngs360.example.com"
        mock_get_settings.return_value = mock_settings

        mock_lambda_client = MagicMock()
        mock_boto3_client.return_value = mock_lambda_client

        run = WorkflowRun(
            id="run-file-fail",
            workflow_url="test-workflow-id",
            workflow_type="CWL",
            workflow_type_version="v1.0",
            workflow_params={"sample_sheet": "ngs360://missing"},
            tags={},
            project="test",
            task_name="test-task",
            system_logs=[],
        )

        with patch.dict('os.environ', {'LAMBDA_FUNCTION_NAME': 'test-function'}):
            service = LambdaWorkflowSubmissionService()

        with patch.object(
            service,
            "_get_engine_id_from_ngs360",
            return_value="arn:aws:omics:us-east-1:123:workflow/456",
        ), patch.object(
            service,
            "_get_s3_uri_from_ngs360",
            side_effect=RuntimeError("NGS360 API returned status 404 for file missing: Not Found"),
        ):
            from unittest.mock import AsyncMock
            mock_db = MagicMock()
            mock_db.commit = AsyncMock()

            await service.submit_workflow(run, mock_db)

        assert run.state == WorkflowState.SYSTEM_ERROR
        assert any(
            "Failed to resolve NGS360 file id" in msg for msg in run.system_logs
        )
        mock_lambda_client.invoke.assert_not_called()
        mock_db.commit.assert_awaited_once()
