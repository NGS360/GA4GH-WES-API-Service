"""
SevenBridges/Velsera workflow provider implementation
"""
import os
import logging
from typing import Dict, List, Tuple, Any
from datetime import datetime

# Note: This requires the sevenbridges-python package to be installed
# We'll need to add it to requirements.txt
try:
    from sevenbridges.api import Api
    from sevenbridges.errors import SbgError
    SEVENBRIDGES_AVAILABLE = True
except ImportError:
    SEVENBRIDGES_AVAILABLE = False

from app.models.workflow import WorkflowRun
from .provider_interface import WorkflowProviderInterface


class SevenBridgesProvider(WorkflowProviderInterface):
    """SevenBridges/Velsera workflow provider implementation"""
    
    def __init__(self):
        """Initialize the SevenBridges API client"""
        self.logger = logging.getLogger(__name__)
        
        if not SEVENBRIDGES_AVAILABLE:
            raise ImportError(
                "sevenbridges-python package is not installed. "
                "Install it with 'pip install sevenbridges-python'"
            )
        
        # Get credentials from environment variables
        token = os.environ.get('SEVENBRIDGES_API_TOKEN')
        endpoint = os.environ.get('SEVENBRIDGES_API_ENDPOINT', 'https://api.sbgenomics.com/v2')
        self.project_id = os.environ.get('SEVENBRIDGES_PROJECT')
        
        if not token:
            raise ValueError("SEVENBRIDGES_API_TOKEN environment variable must be set")
        
        if not self.project_id:
            raise ValueError("SEVENBRIDGES_PROJECT environment variable must be set")
        
        self.logger.info(f"Initializing SevenBridges API client with endpoint {endpoint}")
        self.api = Api(token=token, url=endpoint)
    
    def submit_workflow(self, workflow: WorkflowRun) -> str:
        """Submit a workflow to SevenBridges/Velsera"""
        self.logger.info(f"Submitting workflow {workflow.run_id} to SevenBridges")
        
        # Convert WES workflow to SevenBridges format
        task_inputs = self._convert_workflow_params(workflow.workflow_params)
        
        # Get the app from the workflow_url
        # The workflow_url could be:
        # 1. A direct SB app ID: admin/sbg-public-data/rna-seq-alignment-1-0-2
        # 2. A URL to a CWL file: https://example.com/workflow.cwl
        # 3. A relative path to an uploaded file: workflow.cwl
        app_id = workflow.workflow_url
        
        try:
            # Create and run the task
            task = self.api.tasks.create(
                name=f"WES-{workflow.run_id}",
                project=self.project_id,
                app=app_id,
                inputs=task_inputs,
                description=f"Workflow run {workflow.run_id}"
            )
            
            # Run the task
            task.run()
            
            self.logger.info(f"Submitted workflow {workflow.run_id} to SevenBridges with ID {task.id}")
            return task.id
        except SbgError as e:
            self.logger.error(f"SevenBridges API error: {e}")
            raise RuntimeError(f"Failed to submit workflow to SevenBridges: {e}")
    
    def get_workflow_status(self, provider_id: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
        """Get the status of a workflow from SevenBridges/Velsera"""
        self.logger.debug(f"Checking status of SevenBridges task {provider_id}")
        
        try:
            task = self.api.tasks.get(provider_id)
            
            # Map SevenBridges status to WES status
            status_map = {
                'DRAFT': 'INITIALIZING',
                'CREATING': 'INITIALIZING',
                'QUEUED': 'QUEUED',
                'RUNNING': 'RUNNING',
                'COMPLETED': 'COMPLETE',
                'FAILED': 'EXECUTOR_ERROR',
                'ABORTED': 'CANCELED'
            }
            
            wes_status = status_map.get(task.status, 'UNKNOWN')
            
            # Get outputs if the task is completed
            outputs = {}
            if task.status == 'COMPLETED' and hasattr(task, 'outputs'):
                for key, value in task.outputs.items():
                    if hasattr(value, 'id'):
                        # This is a file
                        outputs[key] = {
                            'id': value.id,
                            'name': value.name,
                            'size': value.size,
                            'url': value.download_url()
                        }
                    else:
                        # This is a primitive value
                        outputs[key] = value
            
            # Get task logs
            task_logs = []
            
            # Try to get execution details if available
            try:
                execution_details = self.api.execution_details.get(task.id)
                if execution_details and hasattr(execution_details, 'jobs'):
                    for job in execution_details.jobs:
                        task_log = {
                            'name': job.name,
                            'start_time': job.start_time.isoformat() if job.start_time else None,
                            'end_time': job.end_time.isoformat() if job.end_time else None,
                            'status': job.status,
                            'command': job.command if hasattr(job, 'command') else None
                        }
                        
                        # Add stdout/stderr if available
                        if hasattr(job, 'stdout'):
                            task_log['stdout'] = job.stdout
                        if hasattr(job, 'stderr'):
                            task_log['stderr'] = job.stderr
                        
                        task_logs.append(task_log)
            except Exception as e:
                self.logger.warning(f"Could not get execution details for task {task.id}: {e}")
            
            return wes_status, outputs, task_logs
        
        except SbgError as e:
            self.logger.error(f"SevenBridges API error: {e}")
            raise RuntimeError(f"Failed to get workflow status from SevenBridges: {e}")
    
    def cancel_workflow(self, provider_id: str) -> bool:
        """Cancel a workflow in SevenBridges/Velsera"""
        self.logger.info(f"Canceling SevenBridges task {provider_id}")
        
        try:
            task = self.api.tasks.get(provider_id)
            if task.status in ['RUNNING', 'QUEUED']:
                task.abort()
                return True
            else:
                self.logger.warning(f"Task {provider_id} is in state {task.status} and cannot be canceled")
                return False
        except SbgError as e:
            self.logger.error(f"Error canceling task {provider_id}: {e}")
            return False
    
    def _convert_workflow_params(self, params: Dict) -> Dict[str, Any]:
        """
        Convert WES workflow parameters to SevenBridges format
        
        Args:
            params: The WES workflow parameters
            
        Returns:
            Dict: The SevenBridges task inputs
        """
        if not params:
            return {}
        
        # This is a simplified implementation
        # In a real implementation, this would handle file references, etc.
        # For example, converting file paths to SevenBridges file objects
        
        sb_inputs = {}
        
        for key, value in params.items():
            # Handle file references
            if isinstance(value, str) and (value.startswith('http://') or 
                                          value.startswith('https://') or 
                                          value.startswith('s3://') or
                                          value.startswith('gs://')):
                # This is likely a file reference
                # In a real implementation, we would need to import the file to SevenBridges
                # or use an existing file ID
                self.logger.warning(f"File reference '{value}' for parameter '{key}' not handled")
                sb_inputs[key] = value
            else:
                # Pass through other values
                sb_inputs[key] = value
        
        return sb_inputs