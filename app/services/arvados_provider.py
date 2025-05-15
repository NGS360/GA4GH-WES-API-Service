"""Arvados Service Provider Implementation"""
import os
import requests
from app.services.provider_interface import WorkflowServiceProvider

class ArvadosProvider(WorkflowServiceProvider):
    """Arvados Service Provider"""
    
    def __init__(self):
        """Initialize the Arvados client"""
        self.api_url = os.environ.get('ARVADOS_API_URL')
        self.api_token = os.environ.get('ARVADOS_API_TOKEN')
        self.headers = {
            'Authorization': f'Bearer {self.api_token}',
            'Content-Type': 'application/json'
        }
    
    def submit_workflow(self, workflow_run):
        """Submit a workflow to Arvados"""
        try:
            # Extract necessary parameters from workflow_run
            workflow_uuid = workflow_run.workflow_params.get('workflow_uuid')
            if not workflow_uuid:
                # Try to extract from URL if not in params
                workflow_uuid = workflow_run.workflow_url.split('/')[-1]
            
            # Prepare the request payload
            payload = {
                'workflow': {
                    'uuid': workflow_uuid,
                    'name': workflow_run.workflow_params.get('name', f"WES Run {workflow_run.run_id}"),
                    'repository': workflow_run.workflow_url,
                    'script_parameters': workflow_run.workflow_params.get('parameters', {}),
                    'runtime_constraints': workflow_run.workflow_params.get('runtime_constraints', {})
                }
            }
            
            # Add provider-specific parameters if available
            provider_params = workflow_run.workflow_params.get('provider_params', {})
            if provider_params:
                for key, value in provider_params.items():
                    if key not in payload['workflow']:
                        payload['workflow'][key] = value
            
            # Submit the workflow
            response = requests.post(
                f"{self.api_url}/arvados/v1/container_requests",
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                'provider_run_id': result['uuid'],
                'status': result['state'],
                'metadata': result
            }
        except requests.RequestException as error:
            raise RuntimeError(f"Failed to submit workflow to Arvados: {str(error)}") from error
    
    def get_run_status(self, workflow_run):
        """Get the status of a workflow run from Arvados"""
        try:
            response = requests.get(
                f"{self.api_url}/arvados/v1/container_requests/{workflow_run.provider_run_id}",
                headers=self.headers
            )
            response.raise_for_status()
            result = response.json()
            
            # Extract outputs if available
            outputs = {}
            if result.get('output'):
                outputs = result['output']
            
            return {
                'status': result['state'],
                'outputs': outputs,
                'metadata': result
            }
        except requests.RequestException as error:
            raise RuntimeError(f"Failed to get run status from Arvados: {str(error)}") from error
    
    def cancel_run(self, workflow_run):
        """Cancel a workflow run in Arvados"""
        try:
            payload = {
                'container_request': {
                    'priority': 0  # Setting priority to 0 cancels the run in Arvados
                }
            }
            
            response = requests.put(
                f"{self.api_url}/arvados/v1/container_requests/{workflow_run.provider_run_id}",
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            
            return True
        except requests.RequestException as error:
            raise RuntimeError(f"Failed to cancel run in Arvados: {str(error)}") from error
    
    def map_status_to_wes(self, provider_status):
        """Map Arvados status to WES status"""
        status_map = {
            'Uncommitted': 'QUEUED',
            'Committed': 'INITIALIZING',
            'Queued': 'QUEUED',
            'Locked': 'INITIALIZING',
            'Running': 'RUNNING',
            'Complete': 'COMPLETE',
            'Cancelled': 'CANCELED',
            'Failed': 'EXECUTOR_ERROR'
        }
        return status_map.get(provider_status, 'UNKNOWN')