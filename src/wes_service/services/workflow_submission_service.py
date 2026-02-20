"""Service layer for workflow submission operations."""

import asyncio
import boto3
import json
import logging
import os
import requests
from abc import ABC, abstractmethod

from src.wes_service.config import get_settings
from src.wes_service.db.models import WorkflowRun

logger = logging.getLogger(__name__)


class WorkflowSubmissionService(ABC):
    """Abstract base class for workflow submission services."""

    @abstractmethod
    async def submit_workflow(self, run: WorkflowRun) -> dict:
        """
        Submit workflow for execution.

        Args:
            run: WorkflowRun to submit

        Returns:
            Response containing execution details (e.g., omics_run_id)

        Raises:
            Exception: If submission fails
        """
        pass


class LambdaWorkflowSubmissionService(WorkflowSubmissionService):
    """Workflow submission service using AWS Lambda."""

    def __init__(self):
        """Initialize Lambda workflow submission service."""
        # Initialize Lambda client for workflow submission using environment variables
        lambda_region = os.environ.get('LAMBDA_REGION', 'us-east-1')
        self.lambda_client = boto3.client('lambda', region_name=lambda_region)

        # Get Lambda function name from environment variable
        self.lambda_function_name = os.environ.get('LAMBDA_FUNCTION_NAME')

        # Get NGS360 API URL from settings (same pattern as omics.py)
        settings = get_settings()
        self.ngs360_api_url = settings.ngs360_api_url

    async def submit_workflow(self, run: WorkflowRun) -> dict:
        """
        Submit workflow to Lambda function for Omics execution.

        Args:
            run: WorkflowRun to submit

        Returns:
            Lambda response containing omics_run_id

        Raises:
            Exception: If Lambda invocation or workflow submission fails
        """
        try:
            # Get engine_id from NGS360 API using the workflow_url as the workflow ID
            engine_id = await self._get_engine_id_from_ngs360(run.workflow_url)

            # Prepare Lambda payload using the engine_id instead of workflow_id
            lambda_payload = {
                'action': 'submit_workflow',
                'source': 'ga4ghwes',
                'wes_run_id': run.id,
                'workflow_id': engine_id,  # Use engine_id from NGS360 API
                'workflow_version': run.workflow_params.get('workflow_version') if run.workflow_params else None,
                'workflow_type': run.workflow_type,
                'parameters': run.workflow_params or {},
                'workflow_engine_parameters': run.workflow_engine_parameters or {},
                'tags': {
                    **(run.tags or {}),
                    'WESRunId': run.id
                }
            }

            logger.info(f"Lambda payload for run {run.id}: {json.dumps(lambda_payload, default=str)}")

            # Call Lambda function asynchronously
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.lambda_client.invoke(
                    FunctionName=self.lambda_function_name,
                    InvocationType='RequestResponse',
                    Payload=json.dumps(lambda_payload)
                )
            )

            # Parse response
            response_payload = json.loads(response['Payload'].read())

            # Check for errors
            if response['StatusCode'] != 200:
                raise Exception(f"Lambda invocation failed with status {response['StatusCode']}: {response_payload}")

            if response_payload.get('statusCode') != 200:
                error_msg = response_payload.get('message', 'Unknown error')
                raise Exception(f"Workflow submission failed: {error_msg}")

            return response_payload

        except Exception as e:
            logger.error(f"Error calling Lambda function {self.lambda_function_name}: {str(e)}")
            raise

    async def _get_engine_id_from_ngs360(self, workflow_id: str) -> str:
        """
        Query NGS360 API to get the engine_id for a given workflow ID.

        Args:
            workflow_id: The workflow ID to look up

        Returns:
            The engine_id from the NGS360 API

        Raises:
            Exception: If API call fails or engine_id not found
        """
        try:
            # Construct the API URL
            api_url = f"{self.ngs360_api_url}/api/v1/workflows/{workflow_id}"
            logger.info(f"Querying NGS360 API for workflow {workflow_id}: {api_url}")

            # Make async HTTP request
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(api_url)
            )

            if response.status_code != 200:
                raise Exception(f"NGS360 API returned status {response.status_code}: {response.text}")

            workflow_data = response.json()
            engine_id = workflow_data.get("engine_id")

            if not engine_id:
                raise Exception(f"engine_id not found for workflow {workflow_id} in NGS360 API response")

            logger.info(f"Successfully retrieved engine_id '{engine_id}' for workflow {workflow_id}")
            return engine_id

        except Exception as e:
            logger.error(f"Failed to get engine_id for workflow {workflow_id} from NGS360 API: {str(e)}")
            raise
