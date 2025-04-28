"""Workflow Executor Service"""
import time
import logging
from datetime import datetime
from app.models.workflow import WorkflowRun
from app.extensions import DB
from app.services.wes_factory import WesFactory

class WorkflowExecutor:
    """Service to monitor and execute workflow requests from the database"""
    
    def __init__(self, poll_interval=10):
        """Initialize the workflow executor
        
        Args:
            poll_interval: Time in seconds between database polls
        """
        self.poll_interval = poll_interval
        self.logger = logging.getLogger(__name__)
        
    def start(self):
        """Start the workflow executor service"""
        self.logger.info("Starting workflow executor service")
        
        while True:
            try:
                self._process_pending_workflows()
                self._update_running_workflows()
            except Exception as e:
                self.logger.error(f"Error in workflow executor: {str(e)}")
            
            time.sleep(self.poll_interval)
    
    def _process_pending_workflows(self):
        """Process pending workflow requests"""
        # Find workflows that haven't been processed yet
        pending_workflows = WorkflowRun.query.filter_by(processed=False).all()
        
        for workflow in pending_workflows:
            try:
                # Create appropriate WES provider based on workflow engine
                wes_service = WesFactory.create_provider(workflow.workflow_engine)
                
                # Start the workflow
                external_id = wes_service.start_run(
                    workflow_id=workflow.workflow_url,
                    parameters=workflow.workflow_params,
                    output_uri=workflow.workflow_params.get('outputUri'),
                    tags=workflow.tags
                )
                
                # Update the workflow record
                workflow.processed = True
                workflow.processed_at = datetime.utcnow()
                workflow.external_id = external_id
                DB.session.commit()
                
                self.logger.info(f"Started workflow {workflow.run_id} with external ID {external_id}")
            except Exception as e:
                self.logger.error(f"Failed to start workflow {workflow.run_id}: {str(e)}")
                workflow.state = 'SYSTEM_ERROR'
                workflow.error_message = str(e)
                workflow.processed = True
                workflow.processed_at = datetime.utcnow()
                DB.session.commit()
    
    def _update_running_workflows(self):
        """Update status of running workflows"""
        # Find workflows that are in progress
        running_states = ['QUEUED', 'INITIALIZING', 'RUNNING']
        running_workflows = WorkflowRun.query.filter(
            WorkflowRun.state.in_(running_states),
            WorkflowRun.processed == True
        ).all()
        
        for workflow in running_workflows:
            try:
                # Create appropriate WES provider
                wes_service = WesFactory.create_provider(workflow.workflow_engine)
                
                # Get current status
                run_details = wes_service.get_run(workflow.external_id)
                current_state = wes_service.map_run_state(run_details['status'])
                
                # Update if state has changed
                if current_state != workflow.state:
                    workflow.state = current_state
                    
                    # If workflow is complete, update end time
                    if current_state in ['COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']:
                        workflow.end_time = datetime.utcnow()
                    
                    DB.session.commit()
                    self.logger.info(f"Updated workflow {workflow.run_id} state to {current_state}")
            except Exception as e:
                self.logger.error(f"Failed to update workflow {workflow.run_id}: {str(e)}")