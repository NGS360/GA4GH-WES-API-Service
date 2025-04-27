"""AWS HealthOmics Service Integration"""
import os
import boto3
from botocore.exceptions import ClientError

from app.services.wes_provider import WesProvider

class SevenBridgesService(WesProvider):
    """SevenBridges Service wrapper"""
    def __init__(self):
        self.client = boto3.client('omics')

    def start_run(self, workflow_id, parameters=None, output_uri=None, tags=None):
        """Start a workflow run"""
        try:
            request = {
                'workflowId': workflow_id,
                'parameters': parameters or {},
                'outputUri': output_uri,
                'tags': tags or {}
            }
            response = self.client.start_run(**request)
            return response['id']
        except ClientError as error:
            raise RuntimeError(f"Failed to start workflow run: {str(error)}") from error

    def get_run(self, run_id):
        """Get run details"""
        try:
            response = self.client.get_run(id=run_id)
            return response
        except ClientError as error:
            raise RuntimeError(f"Failed to get run {run_id}: {str(error)}") from error

    def list_runs(self, next_token=None, max_results=100):
        """List workflow runs"""
        try:
            params = {'maxResults': max_results}
            if next_token:
                params['startingToken'] = next_token
            response = self.client.list_runs(**params)
            return response
        except ClientError as error:
            raise RuntimeError(f"Failed to list runs: {str(error)}") from error

    def cancel_run(self, run_id):
        """Cancel a workflow run"""
        try:
            self.client.cancel_run(id=run_id)
            return True
        except ClientError as error:
            raise RuntimeError(f"Failed to cancel run {run_id}: {str(error)}") from error

    @staticmethod
    def map_run_state(omics_status):
        """Map AWS HealthOmics run status to WES state"""
        status_map = {
            'PENDING': 'QUEUED',
            'STARTING': 'INITIALIZING',
            'RUNNING': 'RUNNING',
            'STOPPING': 'CANCELING',
            'CANCELLED': 'CANCELLED',
            'COMPLETED': 'COMPLETE',
            'FAILED': 'FAILED'
        }
        return status_map.get(omics_status, 'UNKNOWN')

    def list_run_groups(self, next_token=None, max_results=100):
        """List run groups"""
        try:
            params = {'maxResults': max_results}
            if next_token:
                params['startingToken'] = next_token
            response = self.client.list_run_groups(**params)
            return response
        except ClientError as error:
            raise RuntimeError(f"Failed to list run groups: {str(error)}") from error

    def get_run_group(self, group_id):
        """Get run group details"""
        try:
            response = self.client.get_run_group(id=group_id)
            return response
        except ClientError as error:
            raise RuntimeError(f"Failed to get run group {group_id}: {str(error)}") from error

    def list_runs_in_group(self, group_id, next_token=None, max_results=100):
        """List runs in a specific run group"""
        try:
            params = {
                'runGroupId': group_id,
                'maxResults': max_results
            }
            if next_token:
                params['startingToken'] = next_token
            response = self.client.list_runs(**params)
            return response
        except ClientError as error:
            raise RuntimeError(f"Failed to list runs in group {group_id}: {str(error)}") from error
