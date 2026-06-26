"""Service layer for workflow submission operations."""

import boto3
import json
import logging
import os
import httpx
from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.wes_service.config import get_settings
from src.wes_service.db.models import WorkflowRun

logger = logging.getLogger(__name__)


class WorkflowSubmissionService(ABC):
    """Abstract base class for workflow submission services."""

    @abstractmethod
    async def submit_workflow(self, run: WorkflowRun, db: AsyncSession) -> dict:
        """
        Submit workflow for execution.

        Args:
            run: WorkflowRun to submit
            db: Database session for logging errors

        Returns:
            Response containing execution details (e.g., omics_run_id)

        Raises:
            RuntimeError: If submission fails
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

    async def submit_workflow(self, run_request: WorkflowRun, db: AsyncSession):
        """
        Submit workflow to Lambda function for Omics execution.

        Args:
            run_request_id: ID of the workflow run to submit
            db: Database session for logging errors
        """
        # Get engine_id from NGS360 API using the workflow_url as the workflow ID
        try:
            workflow_engine_id = await self._get_engine_id_from_ngs360(run_request.workflow_url)
        except RuntimeError as e:
            error_msg = (
                f"Failed to retrieve engine_id from NGS360 API for workflow "
                f"{run_request.workflow_url}: {str(e)}"
            )
            logger.error(error_msg)
            return

        settings = get_settings()
        # Prepare Lambda payload
        lambda_payload = {
            'action': 'submit_workflow',
            'source': 'ga4ghwes',
            'wes_run_id': run_request.id,
            'workflow_id': workflow_engine_id,
            'workflow_version': (
                run_request.workflow_params.get('workflow_version')
                if run_request.workflow_params else None
            ),
            'workflow_type': run_request.workflow_type,
            'parameters': run_request.workflow_params or {},
            'workflow_engine_parameters': run_request.workflow_engine_parameters or {},
            'tags': {
                **(run_request.tags or {}),
                'WESRunId': run_request.id,
                'callback_url': settings.client_origin + "/internal/callbacks/omics-state-change"
            }
        }

        logger.info(
            f"Lambda payload for run {run_request.id}: "
            f"{json.dumps(lambda_payload, default=str)}"
        )

        # Call Lambda function asynchronously
        response = self.lambda_client.invoke(
                FunctionName=self.lambda_function_name,
                InvocationType='Event',
                Payload=json.dumps(lambda_payload)
        )
        logger.info(f"Lambda invocation response from {self.lambda_function_name}: {response}")

    async def _get_engine_id_from_ngs360(self, workflow_url: str) -> str:
        """
        Query NGS360 API to get the engine_id for a given workflow URL.

        Args:
            workflow_url: The workflow URL in format NGS360WORKFLOWID[:ALIAS_OR_VERSION]

        Returns:
            The workflow id on the requested engine from the NGS360 API

        Raises:
            RuntimeError: If API call fails or workflow_engine_id not found
        """
        workflow_id, suffix = self._parse_workflow_url(workflow_url)
        workflow_data = await self._fetch_workflow_from_api(workflow_id)
        selected_version = self._select_version(workflow_data, suffix, workflow_id)
        workflow_engine_id = self._select_deployment(selected_version, suffix, workflow_id)

        logger.info(
            f"Successfully retrieved workflow_engine_id "
            f"'{workflow_engine_id}' for workflow {workflow_url}"
        )
        return workflow_engine_id

    def _parse_workflow_url(self, workflow_url: str) -> tuple[str, str | None]:
        """
        Parse workflow URL into ID and optional suffix (alias/version).

        Args:
            workflow_url: The workflow URL in format NGS360WORKFLOWID[:ALIAS_OR_VERSION]

        Returns:
            Tuple of (workflow_id, suffix) where suffix may be None

        Raises:
            RuntimeError: If URL format is invalid
        """
        if ':' not in workflow_url:
            return workflow_url, None

        parts = workflow_url.split(':')
        if len(parts) > 2:
            raise RuntimeError(
                "Workflow URL format error - expect NGS360WORKFLOWID[:ALIAS_OR_VERSION]"
            )
        return parts[0], parts[1]

    async def _fetch_workflow_from_api(self, workflow_id: str) -> dict:
        """
        Fetch workflow data from NGS360 API.

        Args:
            workflow_id: The NGS360 workflow ID

        Returns:
            Workflow data dictionary from the API

        Raises:
            RuntimeError: If API call fails
        """
        api_url = f"{self.ngs360_api_url}/api/v1/workflows/{workflow_id}"
        logger.info(f"Querying NGS360 API for workflow {workflow_id}: {api_url}")

        async with httpx.AsyncClient() as client:
            response = await client.get(api_url)

        if response.status_code != 200:
            raise RuntimeError(
                f"NGS360 API returned status {response.status_code}: {response.text}"
            )
        return response.json()

    def _find_version_by_alias(
        self,
        aliases: list[dict],
        versions: list[dict],
        alias_name: str,
    ) -> dict | None:
        """
        Find version matching the given alias.

        Args:
            aliases: List of alias entries from workflow data
            versions: List of version entries from workflow data
            alias_name: The alias name to search for

        Returns:
            Matching version dict, or None if not found
        """
        if not aliases:
            return None
        for alias_entry in aliases:
            if alias_entry["alias"] == alias_name:
                alias_version = alias_entry["version"]
                matching = [v for v in versions if v["version"] == alias_version]
                return matching[0] if matching else None
        return None

    def _find_version_by_number(
        self,
        versions: list[dict],
        version_str: str,
    ) -> dict | None:
        """
        Find version by direct version number string.

        Args:
            versions: List of version entries from workflow data
            version_str: Version number as a string

        Returns:
            Matching version dict, or None if not found
        """
        for version_entry in versions:
            if str(version_entry["version"]) == version_str:
                return version_entry
        return None

    def _select_version(
        self,
        workflow_data: dict,
        suffix: str | None,
        workflow_id: str,
    ) -> dict:
        """
        Select the appropriate workflow version based on suffix or return latest.

        Args:
            workflow_data: Full workflow data from the API
            suffix: Optional alias or version suffix
            workflow_id: The workflow ID (for error messages)

        Returns:
            Selected version dictionary

        Raises:
            RuntimeError: If no versions exist or specified version not found
        """
        versions = workflow_data.get("versions", [])
        if not versions:
            raise RuntimeError(
                f"No versions found for workflow {workflow_id} in NGS360 API response"
            )

        if not suffix:
            return max(versions, key=lambda v: v["version"])

        # Try alias first, then direct version number
        aliases = workflow_data.get("aliases", [])
        selected = self._find_version_by_alias(aliases, versions, suffix)

        if not selected:
            selected = self._find_version_by_number(versions, suffix)

        if not selected:
            raise RuntimeError(
                f"Specified Alias/Version {suffix} is not found for workflow {workflow_id}."
            )

        return selected

    def _select_deployment(
        self,
        version: dict,
        suffix: str | None,
        workflow_id: str,
    ) -> str:
        """
        Select the most recent AWSHealthOmics deployment and return its engine_id.

        Args:
            version: The selected version dictionary
            suffix: The alias/version suffix (for error messages)
            workflow_id: The workflow ID (for error messages)

        Returns:
            The engine_id string from the selected deployment

        Raises:
            RuntimeError: If no deployments found or engine_id is empty
        """
        deployments = version.get("deployments", [])
        omics_deployments = [
            d for d in deployments
            if d["engine"] == "AWSHealthOmics (us-east)"
        ]

        if not omics_deployments:
            raise RuntimeError(
                f"Specified Alias/Version {suffix} has no deployments "
                f"in AWSHealthOmics (us-east)."
            )

        latest = max(
            omics_deployments,
            key=lambda d: datetime.fromisoformat(d["created_at"]),
        )

        engine_id = latest["external_id"]
        if not engine_id:
            raise RuntimeError(
                f"engine_id not found for workflow {workflow_id} deployment "
                f"{latest['id']} in NGS360 API response"
            )

        return engine_id
