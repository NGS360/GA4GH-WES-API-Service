"""Service layer for workflow submission operations."""

import asyncio
import boto3
import json
import logging
import os
import httpx
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
            RuntimeError: If submission fails
        """
        pass


class OmicsWorkflowSubmissionService(WorkflowSubmissionService):
    """Direct AWS HealthOmics workflow submission service."""

    def __init__(self):
        """Initialize HealthOmics workflow submission service."""
        settings = get_settings()
        self.omics_client = boto3.client(
            'omics', region_name=settings.omics_region
        )
        self.role_arn = settings.omics_role_arn
        self.output_uri = f"s3://{settings.s3_bucket_name}/healthomics-outputs"

    async def submit_workflow(self, run: WorkflowRun) -> dict:
        """
        Submit workflow directly to AWS HealthOmics.

        Args:
            run: WorkflowRun to submit

        Returns:
            Dict containing omics_run_id, or empty dict on failure
        """
        engine_params = run.workflow_engine_parameters or {}
        output_uri = engine_params.get('outputUri', self.output_uri)

        # Build StartRun parameters
        start_run_params = {
            'roleArn': self.role_arn,
            'outputUri': output_uri,
            'tags': {
                'WESRunId': run.id,
                **(run.tags or {}),
            },
        }

        # workflow_url is the HealthOmics workflow ID
        workflow_id = run.workflow_url
        start_run_params['workflowId'] = workflow_id

        # Workflow version from engine params
        if engine_params.get('workflow_version'):
            start_run_params['workflowVersionName'] = (
                engine_params['workflow_version']
            )

        # Run name
        start_run_params['name'] = run.task_name or f'wes-{run.id}'

        # Workflow parameters
        if run.workflow_params:
            start_run_params['parameters'] = run.workflow_params

        # Storage capacity from engine params
        if engine_params.get('storageCapacity'):
            start_run_params['storageCapacity'] = int(
                engine_params['storageCapacity']
            )

        # Log level
        if engine_params.get('logLevel'):
            start_run_params['logLevel'] = engine_params['logLevel']

        logger.info(
            f"Submitting HealthOmics run for WES run {run.id}: "
            f"workflow={workflow_id}, name={start_run_params['name']}"
        )

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.omics_client.start_run(**start_run_params)
            )

            omics_run_id = response.get('id')
            if not omics_run_id:
                logger.error(
                    f"HealthOmics StartRun response missing 'id': {response}"
                )
                return {}

            logger.info(
                f"HealthOmics run started: {omics_run_id} "
                f"for WES run {run.id}"
            )
            return {
                'omics_run_id': omics_run_id,
                'arn': response.get('arn', ''),
                'status': response.get('status', ''),
            }

        except Exception as e:
            logger.error(
                f"Failed to submit HealthOmics run for WES run {run.id}: {e}"
            )
            return {}


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
            Lambda response containing omics_run_id or empty dict on failure
        """
        # Get engine_id from NGS360 API using the workflow_url as the workflow ID
        try:
            engine_id = await self._get_engine_id_from_ngs360(run.workflow_url)
        except RuntimeError as e:
            logger.error(f"Failed to retrieve engine_id for workflow {run.workflow_url}: "
                         f"{str(e)}")
            return {}

        # Prepare Lambda payload using the engine_id instead of workflow_id
        lambda_payload = {
            'action': 'submit_workflow',
            'source': 'ga4ghwes',
            'wes_run_id': run.id,
            'workflow_id': engine_id,  # Use engine_id from NGS360 API
            'workflow_version': (
                run.workflow_params.get('workflow_version')
                if run.workflow_params else None
            ),
            'workflow_type': run.workflow_type,
            'parameters': run.workflow_params or {},
            'workflow_engine_parameters': run.workflow_engine_parameters or {},
            'tags': {
                **(run.tags or {}),
                'WESRunId': run.id
            }
        }

        logger.info(
            f"Lambda payload for run {run.id}: "
            f"{json.dumps(lambda_payload, default=str)}"
        )

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
        logger.info(f"Lambda invocation response: {response}")

        # Check for errors
        if response['StatusCode'] != 200:
            logger.error(
                f"Lambda invocation failed with status {response['StatusCode']}: "
                f"{response}"
            )
            return {}

        # Parse response
        # The payload is the result of the lambda fn calling Omics.
        response_payload = json.loads(response['Payload'].read())
        logger.info(f"Lambda invocation response payload: {response_payload}")

        if response_payload.get('statusCode') != 200:
            error_msg = response_payload.get('message', 'Unknown error')
            logger.error(f"Workflow submission failed: {error_msg}")
            return {}

        return response_payload

    async def _get_engine_id_from_ngs360(self, workflow_id: str) -> str:
        """
        Query NGS360 API to get the engine_id for a given workflow ID.

        Args:
            workflow_id: The workflow ID to look up

        Returns:
            The engine_id from the NGS360 API

        Raises:
            RuntimeError: If API call fails or engine_id not found
        """
        # Construct the API URL
        api_url = f"{self.ngs360_api_url}/api/v1/workflows/{workflow_id}"
        logger.info(f"Querying NGS360 API for workflow {workflow_id}: {api_url}")

        async with httpx.AsyncClient() as client:
            response = await client.get(api_url)

        if response.status_code != 200:
            raise RuntimeError(
                f"NGS360 API returned status {response.status_code}: {response.text}"
            )

        workflow_data = response.json()
        engine_id = workflow_data.get("engine_id")

        if not engine_id:
            raise RuntimeError(
                f"engine_id not found for workflow {workflow_id} in NGS360 API response"
            )

        logger.info(f"Successfully retrieved engine_id '{engine_id}' for workflow {workflow_id}")
        return engine_id


def get_workflow_submission_service() -> WorkflowSubmissionService:
    """
    Factory that returns the appropriate submission service
    based on the WORKFLOW_EXECUTOR setting.
    """
    settings = get_settings()
    if settings.workflow_executor == 'omics':
        return OmicsWorkflowSubmissionService()
    else:
        return LambdaWorkflowSubmissionService()
