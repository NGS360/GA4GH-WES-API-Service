import requests
import time
import os

class WesClient:
    """
    A service-agnostic client for interacting with WES API implementations.
    """
    def __init__(self, base_url=None):
        """
        Initialize the WES client with a base URL.
        If not provided, uses the environment variable WES_API_URL.
        """
        self.base_url = base_url or os.environ.get('WES_API_URL', 'http://localhost:5000/api/ga4gh/wes/v1')
        
    def get_service_info(self):
        """Get information about the WES service"""
        response = requests.get(f"{self.base_url}/service-info")
        response.raise_for_status()
        return response.json()
    
    def list_runs(self):
        """List all workflow runs"""
        response = requests.get(f"{self.base_url}/runs")
        response.raise_for_status()
        return response.json()
    
    def run_workflow(self, workflow_params, workflow_type, workflow_type_version, 
                    workflow_url, tags=None, workflow_engine=None, 
                    workflow_engine_version=None, workflow_engine_parameters=None,
                    workflow_attachment=None):
        """Submit a new workflow run"""
        data = {
            'workflow_params': workflow_params,
            'workflow_type': workflow_type,
            'workflow_type_version': workflow_type_version,
            'workflow_url': workflow_url
        }
        
        if tags:
            data['tags'] = tags
        if workflow_engine:
            data['workflow_engine'] = workflow_engine
        if workflow_engine_version:
            data['workflow_engine_version'] = workflow_engine_version
        if workflow_engine_parameters:
            data['workflow_engine_parameters'] = workflow_engine_parameters
            
        files = {}
        if workflow_attachment:
            for i, attachment in enumerate(workflow_attachment):
                files[f'workflow_attachment[{i}]'] = attachment
                
        if files:
            response = requests.post(f"{self.base_url}/runs", data=data, files=files)
        else:
            response = requests.post(f"{self.base_url}/runs", json=data)
            
        response.raise_for_status()
        return response.json()
    
    def get_run_status(self, run_id):
        """Get the status of a workflow run"""
        response = requests.get(f"{self.base_url}/runs/{run_id}/status")
        response.raise_for_status()
        return response.json()
    
    def get_run_log(self, run_id):
        """Get detailed information about a workflow run"""
        response = requests.get(f"{self.base_url}/runs/{run_id}")
        response.raise_for_status()
        return response.json()
    
    def cancel_run(self, run_id):
        """Cancel a workflow run"""
        response = requests.post(f"{self.base_url}/runs/{run_id}/cancel")
        response.raise_for_status()
        return response.json()
    
    def wait_for_run_completion(self, run_id, timeout=300, poll_interval=5):
        """
        Wait for a workflow run to complete, with timeout.
        
        Args:
            run_id: The ID of the workflow run
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
            
        Returns:
            The final run status
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_run_status(run_id)
            state = status.get('state')
            
            # Check if the run has completed (successfully or not)
            if state in ['COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']:
                return status
                
            # Wait before checking again
            time.sleep(poll_interval)
            
        raise TimeoutError(f"Workflow run {run_id} did not complete within {timeout} seconds")