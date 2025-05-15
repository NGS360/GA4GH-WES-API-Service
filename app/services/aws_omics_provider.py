"""AWS HealthOmics Service Provider Implementation"""
import os
import boto3
from botocore.exceptions import ClientError
from app.services.provider_interface import WorkflowServiceProvider

class AwsOmicsProvider(WorkflowServiceProvider):
    """AWS HealthOmics Service Provider"""
    
    def __init__(self):
        """Initialize the AWS HealthOmics client"""
        self.client = boto3.client('omics')
        self.role_arn = os.environ.get('AWS_OMICS_ROLE_ARN')
        self.output_uri = os.environ.get('AWS_OMICS_OUTPUT_URI')
    
    def submit_workflow(self, workflow_run):
        """Submit a workflow to AWS HealthOmics"""
        try:
            # Extract workflow ID from workflow_url or workflow_params
            # This is a simplified example - you may need to adjust based on your workflow_url format
            workflow_id = workflow_run.workflow_params.get('workflowId')
            if not workflow_id:
                # Try to extract from URL if not in params
                workflow_id = workflow_run.workflow_url.split('/')[-1]
            
            # Prepare parameters
            parameters = workflow_run.workflow_params.get('parameters', {})
            
            # Prepare tags
            tags = workflow_run.tags or {}
            
            # Submit the run
            request = {
                'workflowId': workflow_id,
                'roleArn': self.role_arn,
                'parameters': parameters,
                'outputUri': self.output_uri,
                'tags': tags
            }
            
            # Add optional parameters if provided in workflow_params
            provider_params = workflow_run.workflow_params.get('provider_params', {})
            if provider_params.get('roleArn'):
                request['roleArn'] = provider_params['roleArn']
            if provider_params.get('outputUri'):
                request['outputUri'] = provider_params['outputUri']
            
            response = self.client.start_run(**request)
            
            return {
                'provider_run_id': response['id'],
                'status': response['status'],
                'metadata': response
            }
        except ClientError as error:
            raise RuntimeError(f"Failed to start workflow run: {str(error)}") from error
    
    def get_run_status(self, workflow_run):
        """Get the status of a workflow run from AWS HealthOmics"""
        try:
            response = self.client.get_run(id=workflow_run.provider_run_id)
            
            return {
                'status': response['status'],
                'outputs': response.get('outputUri'),
                'metadata': response
            }
        except ClientError as error:
            raise RuntimeError(f"Failed to get run status: {str(error)}") from error
    
    def cancel_run(self, workflow_run):
        """Cancel a workflow run in AWS HealthOmics"""
        try:
            self.client.cancel_run(id=workflow_run.provider_run_id)
            return True
        except ClientError as error:
            raise RuntimeError(f"Failed to cancel run: {str(error)}") from error
    
    def map_status_to_wes(self, provider_status):
        """Map AWS HealthOmics status to WES status"""
        status_map = {
            'PENDING': 'QUEUED',
            'STARTING': 'INITIALIZING',
            'RUNNING': 'RUNNING',
            'STOPPING': 'CANCELING',
            'CANCELLED': 'CANCELED',
            'COMPLETED': 'COMPLETE',
            'FAILED': 'EXECUTOR_ERROR'
        }
        return status_map.get(provider_status, 'UNKNOWN')