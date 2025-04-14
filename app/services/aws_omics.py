"""AWS HealthOmics Service Integration"""
import os
import boto3
from botocore.exceptions import ClientError

class HealthOmicsService:
    """AWS HealthOmics Service wrapper"""
    def __init__(self):
        self.client = boto3.client('omics')
        
    def start_run(self, workflow_id, role_arn, parameters=None, output_uri=None, tags=None):
        """Start a workflow run"""
        try:
            request = {
                'workflowId': workflow_id,
                'roleArn': role_arn,
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
