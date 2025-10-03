"""AWS Omics workflow executor implementation."""

import boto3
from datetime import datetime
import asyncio
import logging
from typing import Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.wes_service.daemon.executors.base import WorkflowExecutor
from src.wes_service.db.models import TaskLog, WorkflowRun, WorkflowState
from src.wes_service.config import get_settings

logger = logging.getLogger(__name__)


class OmicsExecutor(WorkflowExecutor):
    """Executor for AWS Omics workflows."""
    
    def __init__(self, region_name=None):
        """
        Initialize with AWS region.
        
        Args:
            region_name: AWS region name (defaults to config setting)
        """
        settings = get_settings()
        self.region = region_name or settings.omics_region
        self.role_arn = settings.omics_role_arn
        self.output_bucket = settings.omics_output_bucket
        
        self.omics_client = boto3.client('omics', region_name=self.region)
    
    async def execute(self, db: AsyncSession, run: WorkflowRun) -> None:
        """
        Execute a workflow run on AWS Omics.
        
        Args:
            db: Database session
            run: WorkflowRun to execute
        """
        try:
            # Update state to INITIALIZING
            run.state = WorkflowState.INITIALIZING
            run.system_logs.append(f"Initializing AWS Omics workflow at {datetime.utcnow().isoformat()}")
            await db.commit()
            
            # Extract workflow ID from workflow_url or params
            workflow_id = self._extract_workflow_id(run)
            
            # Extract input file paths
            input_params = run.workflow_params or {}
            
            # Convert WES parameters to Omics format
            omics_params = self._convert_params_to_omics(input_params)
            
            # Update state to RUNNING
            run.state = WorkflowState.RUNNING
            run.start_time = datetime.utcnow()
            run.system_logs.append(f"Started execution at {run.start_time.isoformat()}")
            await db.commit()
            
            # Start the Omics workflow run
            response = self.omics_client.start_run(
                workflowId=workflow_id,
                roleArn=self.role_arn,
                parameters=omics_params,
                outputUri=f"{self.output_bucket}/runs/{run.id}/output/",
                name=f"wes-run-{run.id}"
            )
            
            # Store the Omics run ID
            omics_run_id = response['id']
            run.system_logs.append(f"Started AWS Omics run: {omics_run_id}")
            await db.commit()
            
            # Monitor the run until completion
            final_state = await self._monitor_omics_run(db, run, omics_run_id)
            
            # Update run state based on Omics result
            run.state = final_state
            run.end_time = datetime.utcnow()
            if final_state == WorkflowState.COMPLETE:
                run.exit_code = 0
                # Get outputs from Omics
                outputs = self._get_run_outputs(omics_run_id)
                run.outputs = outputs
                run.system_logs.append(f"Workflow completed successfully at {run.end_time.isoformat()}")
            else:
                run.exit_code = 1
                run.system_logs.append(f"Workflow failed with state {final_state} at {run.end_time.isoformat()}")
            
            await db.commit()
            
        except Exception as e:
            logger.error(f"Error executing Omics run {run.id}: {e}")
            # Handle errors
            run.state = WorkflowState.SYSTEM_ERROR
            run.end_time = datetime.utcnow()
            run.system_logs.append(f"Execution error: {str(e)}")
            run.exit_code = 1
            await db.commit()
            raise
    
    def _extract_workflow_id(self, run: WorkflowRun) -> str:
        """
        Extract Omics workflow ID from run parameters.
        
        Args:
            run: The workflow run
            
        Returns:
            Omics workflow ID
        """
        # Option 1: Extract from workflow_url if it contains the ID
        if run.workflow_url and run.workflow_url.startswith("omics:"):
            return run.workflow_url.split(":")[-1]
        
        # Option 2: Look for workflow_id in parameters
        if run.workflow_params and "workflow_id" in run.workflow_params:
            return run.workflow_params["workflow_id"]
        
        # Option 3: Use the workflow_url directly if it looks like an ID
        return run.workflow_url
    
    def _convert_params_to_omics(self, wes_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert WES parameters to Omics format.
        
        Args:
            wes_params: WES API parameters
            
        Returns:
            Parameters in Omics format
        """
        omics_params = {}
        
        # Map input file paths to Omics parameter format
        for key, value in wes_params.items():
            if key != "workflow_id":  # Skip the workflow_id if present
                if isinstance(value, str) and (value.startswith("s3://") or value.startswith("/")):
                    # This is likely a file path
                    omics_params[key] = value
                else:
                    # Other parameters
                    omics_params[key] = value
        
        return omics_params
    
    async def _monitor_omics_run(self, db: AsyncSession, run: WorkflowRun, omics_run_id: str) -> WorkflowState:
        """
        Monitor Omics run until completion.
        
        Args:
            db: Database session
            run: The workflow run
            omics_run_id: Omics run ID
            
        Returns:
            Final workflow state
        """
        poll_interval = get_settings().daemon_poll_interval
        
        while True:
            # Get run status from Omics
            response = self.omics_client.get_run(id=omics_run_id)
            status = response['status']
            
            # Log status update
            run.system_logs.append(f"Omics status update: {status}")
            await db.commit()
            
            # Update task logs if available
            if 'tasks' in response:
                await self._update_task_logs(db, run, response['tasks'])
            
            # Map Omics status to WES status
            if status == 'COMPLETED':
                return WorkflowState.COMPLETE
            elif status == 'FAILED':
                return WorkflowState.EXECUTOR_ERROR
            elif status == 'CANCELLED':
                return WorkflowState.CANCELED
            elif status in ['STARTING', 'RUNNING', 'PENDING']:
                # Still running, wait and check again
                await asyncio.sleep(poll_interval)
            else:
                # Unknown status
                run.system_logs.append(f"Unknown Omics status: {status}")
                return WorkflowState.SYSTEM_ERROR
    
    async def _update_task_logs(self, db: AsyncSession, run: WorkflowRun, tasks: list) -> None:
        """
        Update task logs from Omics tasks.
        
        Args:
            db: Database session
            run: The workflow run
            tasks: Omics task data
        """
        for task_data in tasks:
            # Create task ID
            task_id = f"omics-{task_data['id']}"
            
            # Parse dates if available
            start_time = None
            if 'startTime' in task_data:
                try:
                    start_time = datetime.fromisoformat(task_data['startTime'].replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    pass
                    
            end_time = None
            if 'stopTime' in task_data:
                try:
                    end_time = datetime.fromisoformat(task_data['stopTime'].replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    pass
            
            # Create or update task log
            task = TaskLog(
                id=task_id,
                run_id=run.id,
                name=task_data.get('name', 'Unknown task'),
                cmd=[],  # Omics doesn't expose the command
                start_time=start_time,
                end_time=end_time,
                exit_code=0 if task_data.get('status') == 'COMPLETED' else 1,
                system_logs=[f"Omics task status: {task_data.get('status')}"]
            )
            
            db.add(task)
        
        await db.commit()
    
    def _get_run_outputs(self, omics_run_id: str) -> Dict[str, Any]:
        """
        Get outputs from completed Omics run.
        
        Args:
            omics_run_id: Omics run ID
            
        Returns:
            Dictionary of outputs
        """
        try:
            response = self.omics_client.get_run(id=omics_run_id)
            
            # Extract output information
            outputs = {}
            if 'outputUri' in response:
                outputs['output_location'] = response['outputUri']
                
            # Add run logs location
            if 'logUri' in response:
                outputs['log_location'] = response['logUri']
                
            # Add any metrics or statistics if available
            if 'storageCapacity' in response:
                outputs['storage_used_gb'] = response['storageCapacity']
                
            # Add any other output information available
            
            return outputs
        except Exception as e:
            logger.error(f"Error getting outputs for Omics run {omics_run_id}: {e}")
            return {"error": str(e)}