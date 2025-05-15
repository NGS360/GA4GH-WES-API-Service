"""SevenBridges/Velsera Service Provider Implementation"""
import os
import requests
from app.services.provider_interface import WorkflowServiceProvider

class SevenBridgesProvider(WorkflowServiceProvider):
    """SevenBridges/Velsera Service Provider"""
    
    def __init__(self):
        """Initialize the SevenBridges client"""
        self.api_url = os.environ.get('SEVENBRIDGES_API_URL')
        self.api_token = os.environ.get('SEVENBRIDGES_API_TOKEN')
        self.project = os.environ.get('SEVENBRIDGES_PROJECT')
        self.headers = {
            'X-SBG-Auth-Token': self.api_token,
            'Content-Type': 'application/json'
        }
    
    def submit_workflow(self, workflow_run):
        """Submit a workflow to SevenBridges/Velsera"""
        try:
            # Extract necessary parameters from workflow_run
            app_id = workflow_run.workflow_params.get('app_id')
            if not app_id:
                # Try to extract from URL if not in params
                app_id = workflow_run.workflow_url.split('/')[-1]
            
            # Prepare the request payload
            payload = {
                'name': workflow_run.workflow_params.get('name', f"WES Run {workflow_run.run_id}"),
                'app': app_id,
                'project': workflow_run.workflow_params.get('project', self.project),
                'inputs': workflow_run.workflow_params.get('inputs', {})
            }
            
            # Add provider-specific parameters if available
            provider_params = workflow_run.workflow_params.get('provider_params', {})
            if provider_params:
                for key, value in provider_params.items():
                    if key not in payload:
                        payload[key] = value
            
            # Submit the workflow
            response = requests.post(
                f"{self.api_url}/tasks",
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            
            return {
                'provider_run_id': result['id'],
                'status': result['status'],
                'metadata': result
            }
        except requests.RequestException as error:
            raise RuntimeError(f"Failed to submit workflow to SevenBridges: {str(error)}") from error
    
    def get_run_status(self, workflow_run):
        """Get the status of a workflow run from SevenBridges/Velsera"""
        try:
            response = requests.get(
                f"{self.api_url}/tasks/{workflow_run.provider_run_id}",
                headers=self.headers
            )
            response.raise_for_status()
            result = response.json()
            
            # Extract outputs if available
            outputs = {}
            if result.get('outputs'):
                outputs = result['outputs']
            
            return {
                'status': result['status'],
                'outputs': outputs,
                'metadata': result
            }
        except requests.RequestException as error:
            raise RuntimeError(f"Failed to get run status from SevenBridges: {str(error)}") from error
    
    def cancel_run(self, workflow_run):
        """Cancel a workflow run in SevenBridges/Velsera"""
        try:
            response = requests.post(
                f"{self.api_url}/tasks/{workflow_run.provider_run_id}/actions/abort",
                headers=self.headers
            )
            response.raise_for_status()
            
            return True
        except requests.RequestException as error:
            raise RuntimeError(f"Failed to cancel run in SevenBridges: {str(error)}") from error
    
    def map_status_to_wes(self, provider_status):
        """Map SevenBridges/Velsera status to WES status"""
        status_map = {
            'DRAFT': 'QUEUED',
            'CREATING': 'INITIALIZING',
            'QUEUED': 'QUEUED',
            'RUNNING': 'RUNNING',
            'COMPLETED': 'COMPLETE',
            'ABORTED': 'CANCELED',
            'FAILED': 'EXECUTOR_ERROR'
        }
        return status_map.get(provider_status, 'UNKNOWN')