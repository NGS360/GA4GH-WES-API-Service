"""Service layer for workflow submission operations."""

import asyncio
import boto3
import json
import logging
import os
from abc import ABC, abstractmethod

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
            # Extract workflow ID - for now use workflow_url directly
            # In the future this could call NGS360 API to get engine_id
            workflow_id = run.workflow_url

            # Prepare Lambda payload
            lambda_payload = {
                'action': 'submit_workflow',
                'source': 'ga4ghwes',
                'wes_run_id': run.id,
                'workflow_id': workflow_id,
                'workflow_version': run.workflow_params.get('workflow_version') if run.workflow_params else None,
                'workflow_type': run.workflow_type,
                'parameters': run.workflow_params or {},
                'workflow_engine_parameters': run.workflow_engine_parameters or {},
                'tags': {
                    **(run.tags or {}),
                    'WESRunId': run.id
                }
            }
            logger.info('checkpoint1')
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
