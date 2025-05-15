"""
Arvados workflow provider implementation
"""
import os
import logging
from typing import Dict, List, Tuple, Any
from datetime import datetime

# Note: This requires the python-arvados-client package to be installed
try:
    import arvados
    ARVADOS_AVAILABLE = True
except ImportError:
    ARVADOS_AVAILABLE = False

from app.models.workflow import WorkflowRun
from .provider_interface import WorkflowProviderInterface


class ArvadosProvider(WorkflowProviderInterface):
    """Arvados workflow provider implementation"""
    
    def __init__(self):
        """Initialize the Arvados API client"""
        self.logger = logging.getLogger(__name__)
        
        if not ARVADOS_AVAILABLE:
            raise ImportError(
                "python-arvados-client package is not installed. "
                "Install it with 'pip install python-arvados-client'"
            )
        
        # Get credentials from environment variables
        self.api_host = os.environ.get('ARVADOS_API_HOST')
        self.api_token = os.environ.get('ARVADOS_API_TOKEN')
        self.project_uuid = os.environ.get('ARVADOS_PROJECT_UUID')
        
        if not self.api_host:
            raise ValueError("ARVADOS_API_HOST environment variable must be set")
        
        if not self.api_token:
            raise ValueError("ARVADOS_API_TOKEN environment variable must be set")
        
        if not self.project_uuid:
            raise ValueError("ARVADOS_PROJECT_UUID environment variable must be set")
        
        # Configure Arvados API
        arvados.config.settings()['ARVADOS_API_HOST'] = self.api_host
        arvados.config.settings()['ARVADOS_API_TOKEN'] = self.api_token
        
        self.logger.info(f"Initializing Arvados API client with host {self.api_host}")
        self.api = arvados.api('v1')
    
    def submit_workflow(self, workflow: WorkflowRun) -> str:
        """Submit a workflow to Arvados"""
        self.logger.info(f"Submitting workflow {workflow.run_id} to Arvados")
        
        # Convert WES workflow to Arvados format
        container_request = self._convert_workflow_to_container_request(workflow)
        
        try:
            # Create the container request
            response = self.api.container_requests().create(
                body=container_request
            ).execute()
            
            container_uuid = response['uuid']
            self.logger.info(f"Submitted workflow {workflow.run_id} to Arvados with ID {container_uuid}")
            return container_uuid
        except Exception as e:
            self.logger.error(f"Arvados API error: {e}")
            raise RuntimeError(f"Failed to submit workflow to Arvados: {e}")
    
    def get_workflow_status(self, provider_id: str) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]]]:
        """Get the status of a workflow from Arvados"""
        self.logger.debug(f"Checking status of Arvados container request {provider_id}")
        
        try:
            # Get the container request
            container_request = self.api.container_requests().get(
                uuid=provider_id
            ).execute()
            
            # Get the container if available
            container = None
            if container_request.get('container_uuid'):
                try:
                    container = self.api.containers().get(
                        uuid=container_request['container_uuid']
                    ).execute()
                except Exception as e:
                    self.logger.warning(f"Error getting container: {e}")
            
            # Map Arvados state to WES state
            state = self._map_state(container_request, container)
            
            # Get outputs if the container request is complete
            outputs = {}
            if state == 'COMPLETE' and container_request.get('output_uuid'):
                try:
                    # Get the output collection
                    collection = self.api.collections().get(
                        uuid=container_request['output_uuid']
                    ).execute()
                    
                    # Create output URLs
                    outputs = {
                        'output_collection': {
                            'uuid': collection['uuid'],
                            'name': collection.get('name', 'Output'),
                            'url': f"https://{self.api_host}/collections/{collection['uuid']}"
                        }
                    }
                except Exception as e:
                    self.logger.warning(f"Error getting output collection: {e}")
            
            # Get task logs
            task_logs = []
            
            # Add container request log
            task_logs.append({
                'name': 'container_request',
                'start_time': container_request.get('created_at'),
                'end_time': container_request.get('modified_at'),
                'status': container_request.get('state'),
                'exit_code': None
            })
            
            # Add container log if available
            if container:
                task_logs.append({
                    'name': 'container',
                    'start_time': container.get('started_at'),
                    'end_time': container.get('finished_at'),
                    'status': container.get('state'),
                    'exit_code': container.get('exit_code'),
                    'log': f"https://{self.api_host}/containers/{container['uuid']}/log"
                })
            
            return state, outputs, task_logs
        
        except Exception as e:
            self.logger.error(f"Arvados API error: {e}")
            raise RuntimeError(f"Failed to get workflow status from Arvados: {e}")
    
    def cancel_workflow(self, provider_id: str) -> bool:
        """Cancel a workflow in Arvados"""
        self.logger.info(f"Canceling Arvados container request {provider_id}")
        
        try:
            # Update the container request state to Cancelled
            self.api.container_requests().update(
                uuid=provider_id,
                body={'priority': 0}  # Setting priority to 0 cancels the container
            ).execute()
            return True
        except Exception as e:
            self.logger.error(f"Error canceling container request {provider_id}: {e}")
            return False
    
    def _convert_workflow_to_container_request(self, workflow: WorkflowRun) -> Dict[str, Any]:
        """
        Convert a WES workflow to an Arvados container request
        
        Args:
            workflow: The WES workflow
            
        Returns:
            Dict: The Arvados container request
        """
        # Determine if this is a CWL or WDL workflow
        workflow_type = workflow.workflow_type.upper()
        
        if workflow_type == 'CWL':
            return self._convert_cwl_workflow(workflow)
        elif workflow_type == 'WDL':
            return self._convert_wdl_workflow(workflow)
        else:
            raise ValueError(f"Unsupported workflow type: {workflow_type}")
    
    def _convert_cwl_workflow(self, workflow: WorkflowRun) -> Dict[str, Any]:
        """
        Convert a CWL workflow to an Arvados container request
        
        Args:
            workflow: The WES workflow
            
        Returns:
            Dict: The Arvados container request
        """
        # Basic container request structure for CWL
        container_request = {
            'name': f"WES-{workflow.run_id}",
            'description': f"Workflow run {workflow.run_id}",
            'properties': {
                'wes_run_id': workflow.run_id
            },
            'state': 'Uncommitted',
            'priority': 500,  # Normal priority
            'owner_uuid': self.project_uuid,
            'container_image': 'arvados/jobs:latest',
            'cwd': '/var/spool/cwl',
            'output_path': '/var/spool/cwl',
            'scheduling_parameters': {
                'preemptible': False
            },
            'runtime_constraints': {
                'vcpus': 1,
                'ram': 1024 * 1024 * 1024  # 1 GB in bytes
            },
            'mounts': {
                '/var/spool/cwl': {
                    'kind': 'tmp',
                    'capacity': 1024 * 1024 * 1024  # 1 GB in bytes
                }
            },
            'secret_mounts': {}
        }
        
        # Handle workflow URL
        workflow_url = workflow.workflow_url
        
        # If the workflow_url is an Arvados collection, use it directly
        if workflow_url.startswith('arvados:'):
            # Extract the collection UUID and path
            parts = workflow_url.replace('arvados:', '').split('/', 1)
            collection_uuid = parts[0]
            path_in_collection = parts[1] if len(parts) > 1 else ''
            
            # Add the workflow collection to mounts
            container_request['mounts']['/var/lib/cwl/workflow'] = {
                'kind': 'collection',
                'uuid': collection_uuid,
                'path': path_in_collection
            }
            
            # Set the command to run the workflow
            container_request['command'] = [
                'arvados-cwl-runner',
                '--api=containers',
                '--no-wait',
                '/var/lib/cwl/workflow',
                '/var/spool/cwl/cwl.input.json'
            ]
        else:
            # For external URLs, we need to download the workflow first
            container_request['command'] = [
                'bash', '-c',
                f"cd /var/spool/cwl && "
                f"curl -L -o workflow.cwl '{workflow_url}' && "
                f"arvados-cwl-runner --api=containers --no-wait workflow.cwl cwl.input.json"
            ]
        
        # Convert workflow parameters to CWL input JSON
        if workflow.workflow_params:
            container_request['environment'] = {
                'ARVADOS_API_HOST': self.api_host,
                'ARVADOS_API_TOKEN': self.api_token,
                'CWLINPUT': self._format_json(workflow.workflow_params)
            }
        
        # Add any tags as properties
        if workflow.tags:
            for key, value in workflow.tags.items():
                if isinstance(value, (str, int, float, bool)):
                    container_request['properties'][key] = str(value)
        
        return container_request
    
    def _convert_wdl_workflow(self, workflow: WorkflowRun) -> Dict[str, Any]:
        """
        Convert a WDL workflow to an Arvados container request
        
        Args:
            workflow: The WES workflow
            
        Returns:
            Dict: The Arvados container request
        """
        # Basic container request structure for WDL using Cromwell
        container_request = {
            'name': f"WES-{workflow.run_id}",
            'description': f"Workflow run {workflow.run_id}",
            'properties': {
                'wes_run_id': workflow.run_id
            },
            'state': 'Uncommitted',
            'priority': 500,  # Normal priority
            'owner_uuid': self.project_uuid,
            'container_image': 'broadinstitute/cromwell:latest',
            'cwd': '/var/spool/wdl',
            'output_path': '/var/spool/wdl/outputs',
            'scheduling_parameters': {
                'preemptible': False
            },
            'runtime_constraints': {
                'vcpus': 2,
                'ram': 2 * 1024 * 1024 * 1024  # 2 GB in bytes
            },
            'mounts': {
                '/var/spool/wdl': {
                    'kind': 'tmp',
                    'capacity': 2 * 1024 * 1024 * 1024  # 2 GB in bytes
                }
            },
            'secret_mounts': {}
        }
        
        # Handle workflow URL
        workflow_url = workflow.workflow_url
        
        # Command to run the workflow
        container_request['command'] = [
            'bash', '-c',
            f"cd /var/spool/wdl && "
            f"curl -L -o workflow.wdl '{workflow_url}' && "
            f"curl -L -o inputs.json '{self._create_temp_json(workflow.workflow_params)}' && "
            f"java -jar /app/cromwell.jar run workflow.wdl -i inputs.json"
        ]
        
        # Add any tags as properties
        if workflow.tags:
            for key, value in workflow.tags.items():
                if isinstance(value, (str, int, float, bool)):
                    container_request['properties'][key] = str(value)
        
        return container_request
    
    def _map_state(self, container_request: Dict[str, Any], container: Dict[str, Any] = None) -> str:
        """
        Map Arvados state to WES state
        
        Args:
            container_request: The Arvados container request
            container: The Arvados container (if available)
            
        Returns:
            str: The WES state
        """
        cr_state = container_request.get('state', '')
        
        # Map container request state
        if cr_state == 'Final':
            # Check container state for more details
            if container:
                c_state = container.get('state', '')
                exit_code = container.get('exit_code')
                
                if c_state == 'Complete' and exit_code == 0:
                    return 'COMPLETE'
                elif c_state == 'Cancelled':
                    return 'CANCELED'
                else:
                    return 'EXECUTOR_ERROR'
            else:
                # No container, but request is final - likely an error
                return 'SYSTEM_ERROR'
        elif cr_state == 'Committed':
            return 'RUNNING'
        elif cr_state == 'Uncommitted':
            return 'QUEUED'
        else:
            return 'UNKNOWN'
    
    def _format_json(self, data: Dict) -> str:
        """
        Format a dictionary as a JSON string
        
        Args:
            data: The dictionary to format
            
        Returns:
            str: The formatted JSON string
        """
        import json
        return json.dumps(data)
    
    def _create_temp_json(self, data: Dict) -> str:
        """
        Create a temporary JSON file and return its URL
        This is a placeholder - in a real implementation, you would
        upload the JSON to a temporary location accessible by the container
        
        Args:
            data: The data to write to the JSON file
            
        Returns:
            str: The URL of the temporary JSON file
        """
        # In a real implementation, you would upload the JSON to a temporary location
        # For now, we'll just return a placeholder
        return "data:application/json," + self._format_json(data)