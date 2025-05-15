"""
AWS HealthOmics workflow provider implementation
"""
import os
import logging
from typing import Dict, List, Tuple, Any
from datetime import datetime

# Note: This requires the boto3 package to be installed
try:
    import boto3
    import botocore.exceptions
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

from app.models.workflow import WorkflowRun
from .provider_interface import WorkflowProviderInterface


class HealthOmicsProvider(WorkflowProviderInterface):
    """AWS HealthOmics workflow provider implementation"""
    
    def __init__(self):
        """Initialize the AWS HealthOmics client"""
        self.logger = logging.getLogger(__name__)
        
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 package is not installed. "
                "Install it with 'pip install boto3'"
            )
        
        # AWS credentials are expected to be in the environment
        # or in the AWS credentials file
        region = os.environ.get('AWS_REGION', 'us-east-1')
        
        # Check if we have the required environment variables
        if not os.environ.get('AWS_ACCESS_KEY_ID') and not os.path.exists(os.path.expanduser('~/.aws/credentials')):
            self.logger.warning("AWS_ACCESS_KEY_ID not set and no AWS credentials file found")
        
        self.logger.info(f"Initializing AWS HealthOmics client in region {region}")
        self.client = boto3.client('omics', region_name=region)
        
        # Get the workflow role ARN
        self.workflow_role_arn = os.environ.get('AWS_HEALTHOMICS_WORKFLOW_ROLE_ARN')
        if not self.workflow_role_arn:
            self.logger.warning("AWS_HEALTHOMICS_WORKFLOW_ROLE_ARN not set, workflow runs may fail")
        
        # Get the output URI prefix
        self.output_uri = os.environ.get('AWS_HEALTHOMICS_OUTPUT_URI')
        if not self.output_uri:
            self.logger.warning("AWS_HEALTHOMICS_OUTPUT_URI not set, workflow runs may fail")
    
    def submit_workflow(self, workflow: WorkflowRun) -> str:
        """Submit a workflow to AWS HealthOmics"""
        self.logger.info(f"Submitting workflow {workflow.run_id} to AWS HealthOmics")
        
        # Convert WES workflow to HealthOmics format
        run_params = self._convert_workflow_params(workflow.workflow_params)
        
        # The workflow_url in this case should be the workflow ID in HealthOmics
        # If it's not, we'll need to handle that
        workflow_id = workflow.workflow_url
        
        # If the workflow_url is a URL or file path, we'd need to import it first
        # This is a simplified implementation
        if workflow_id.startswith('http://') or workflow_id.startswith('https://') or workflow_id.startswith('/'):
            self.logger.warning(f"workflow_url '{workflow_id}' appears to be a URL or file path, not a workflow ID")
            self.logger.warning("This implementation expects workflow_url to be a HealthOmics workflow ID")
            raise ValueError("workflow_url must be a HealthOmics workflow ID")
        
        try:
            # Create the run request
            request = {
                'workflowId': workflow_id,
                'name': f"WES-{workflow.run_id}",
                'parameters': run_params,
                'tags': {
                    'WES-RunId': workflow.run_id
                }
            }
            
            # Add role ARN if available
            if self.workflow_role_arn:
                request['roleArn'] = self.workflow_role_arn
            
            # Add output URI if available
            if self.output_uri:
                request['outputUri'] = f"{self.output_uri}/{workflow.run_id}"
            
            # Start the run
            response = self.client.start_run(**request)
            
            run_id = response['id']
            self.logger.info(f"Submitted workflow {workflow.run_id} to HealthOmics with ID {run_id}")
            return run_id
        
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"AWS HealthOmics API error: {e}")
            raise RuntimeError(f"Failed to submit workflow to AWS HealthOmics: {e}")
    
    def get_workflow_status(self, provider_id: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
        """Get the status of a workflow from AWS HealthOmics"""
        self.logger.debug(f"Checking status of HealthOmics run {provider_id}")
        
        try:
            response = self.client.get_run(id=provider_id)
            
            # Map HealthOmics status to WES status
            status_map = {
                'PENDING': 'QUEUED',
                'STARTING': 'INITIALIZING',
                'RUNNING': 'RUNNING',
                'COMPLETED': 'COMPLETE',
                'FAILED': 'EXECUTOR_ERROR',
                'CANCELLED': 'CANCELED'
            }
            
            wes_status = status_map.get(response['status'], 'UNKNOWN')
            
            # Get outputs if the run is completed
            outputs = {}
            if response['status'] == 'COMPLETED' and 'output' in response:
                outputs = response['output']
            
            # Get task logs
            task_logs = []
            
            # Try to get tasks if available
            try:
                # List tasks for this run
                tasks_response = self.client.list_run_tasks(
                    id=provider_id,
                    maxResults=100  # Adjust as needed
                )
                
                for task in tasks_response.get('items', []):
                    task_log = {
                        'name': task.get('name', 'Unknown'),
                        'start_time': task.get('startTime', '').isoformat() if task.get('startTime') else None,
                        'end_time': task.get('stopTime', '').isoformat() if task.get('stopTime') else None,
                        'status': task.get('status', 'UNKNOWN'),
                    }
                    
                    # Add log URI if available
                    if 'logStream' in task:
                        log_group = task.get('logGroup', '')
                        log_stream = task.get('logStream', '')
                        if log_group and log_stream:
                            # Create CloudWatch Logs URL
                            region = os.environ.get('AWS_REGION', 'us-east-1')
                            task_log['stdout'] = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group}/log-events/{log_stream}"
                    
                    task_logs.append(task_log)
                
                # Handle pagination if needed
                while 'nextToken' in tasks_response:
                    tasks_response = self.client.list_run_tasks(
                        id=provider_id,
                        maxResults=100,
                        nextToken=tasks_response['nextToken']
                    )
                    
                    for task in tasks_response.get('items', []):
                        task_log = {
                            'name': task.get('name', 'Unknown'),
                            'start_time': task.get('startTime', '').isoformat() if task.get('startTime') else None,
                            'end_time': task.get('stopTime', '').isoformat() if task.get('stopTime') else None,
                            'status': task.get('status', 'UNKNOWN'),
                        }
                        
                        # Add log URI if available
                        if 'logStream' in task:
                            log_group = task.get('logGroup', '')
                            log_stream = task.get('logStream', '')
                            if log_group and log_stream:
                                # Create CloudWatch Logs URL
                                region = os.environ.get('AWS_REGION', 'us-east-1')
                                task_log['stdout'] = f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group}/log-events/{log_stream}"
                        
                        task_logs.append(task_log)
            
            except Exception as e:
                self.logger.warning(f"Could not get tasks for run {provider_id}: {e}")
            
            return wes_status, outputs, task_logs
        
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"AWS HealthOmics API error: {e}")
            raise RuntimeError(f"Failed to get workflow status from AWS HealthOmics: {e}")
    
    def cancel_workflow(self, provider_id: str) -> bool:
        """Cancel a workflow in AWS HealthOmics"""
        self.logger.info(f"Canceling HealthOmics run {provider_id}")
        
        try:
            self.client.cancel_run(id=provider_id)
            return True
        except botocore.exceptions.ClientError as e:
            self.logger.error(f"Error canceling run {provider_id}: {e}")
            return False
    
    def _convert_workflow_params(self, params: Dict) -> Dict[str, Any]:
        """
        Convert WES workflow parameters to HealthOmics format
        
        Args:
            params: The WES workflow parameters
            
        Returns:
            Dict: The HealthOmics run parameters
        """
        if not params:
            return {}
        
        # This is a simplified implementation
        # In a real implementation, this would handle file references, etc.
        # For example, converting S3 URLs to the format expected by HealthOmics
        
        # For now, we'll just pass through the parameters
        return params