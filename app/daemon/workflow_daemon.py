"""
Core daemon implementation for workflow submission and monitoring
"""
import os
import time
import uuid
import logging
import datetime
import traceback
from typing import Dict, List, Optional, Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError

from app.models.workflow import WorkflowRun, TaskLog
from app.daemon.providers.provider_factory import ProviderFactory
from app.daemon.notification_server import NotificationServer


class WorkflowDaemon:
    """Daemon for submitting and monitoring workflows"""
    
    def __init__(self, db_uri: str):
        """
        Initialize the workflow daemon
        
        Args:
            db_uri: The database URI
        """
        self.logger = logging.getLogger(__name__)
        self.db_uri = db_uri
        
        # Create database engine and session
        self.engine = create_engine(db_uri)
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        
        # Configuration from environment variables
        self.poll_interval = int(os.environ.get('DAEMON_POLL_INTERVAL', '300'))  # Default to 5 minutes since we'll use notifications
        self.status_check_interval = int(os.environ.get('DAEMON_STATUS_CHECK_INTERVAL', '300'))
        self.max_concurrent_workflows = int(os.environ.get('DAEMON_MAX_CONCURRENT_WORKFLOWS', '10'))
        
        # Notification server configuration
        self.notification_host = os.environ.get('DAEMON_NOTIFICATION_HOST', 'localhost')
        self.notification_port = int(os.environ.get('DAEMON_NOTIFICATION_PORT', '5001'))
        
        # Initialize notification server
        self.notification_server = NotificationServer(
            host=self.notification_host,
            port=self.notification_port,
            callback=self.process_workflow_by_id
        )
        
        # Track when we last checked each workflow's status
        self.last_status_check: Dict[str, float] = {}
        
        # Flag to control daemon execution
        self.running = False
        
        self.logger.info(f"Initialized workflow daemon with poll interval {self.poll_interval}s")
        self.logger.info(f"Status check interval: {self.status_check_interval}s")
        self.logger.info(f"Max concurrent workflows: {self.max_concurrent_workflows}")
        self.logger.info(f"Notification server will listen on {self.notification_host}:{self.notification_port}")
    
    def run(self):
        """Run the daemon"""
        self.logger.info("Starting workflow daemon")
        self.running = True
        
        # Start notification server
        try:
            self.notification_server.start()
        except Exception as e:
            self.logger.error(f"Failed to start notification server: {e}")
            self.logger.error("Daemon will continue with polling only")
        
        try:
            while self.running:
                try:
                    # Poll for new workflows (as a fallback mechanism)
                    self.poll_for_workflows()
                    
                    # Check status of running workflows
                    self.check_workflow_status()
                    
                    # Sleep before next poll
                    time.sleep(self.poll_interval)
                except Exception as e:
                    self.logger.error(f"Error in daemon main loop: {e}")
                    self.logger.error(traceback.format_exc())
                    # Continue running despite errors
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, shutting down")
            self.running = False
        finally:
            # Stop notification server
            if self.notification_server:
                try:
                    self.notification_server.stop()
                except Exception as e:
                    self.logger.error(f"Error stopping notification server: {e}")
        
        self.logger.info("Workflow daemon stopped")
    
    def stop(self):
        """Stop the daemon"""
        self.logger.info("Stopping workflow daemon")
        self.running = False
    
    def process_workflow_by_id(self, run_id: str):
        """
        Process a specific workflow by ID (called by notification server)
        
        Args:
            run_id: The ID of the workflow to process
        """
        self.logger.info(f"Received notification to process workflow {run_id}")
        
        session = self.Session()
        try:
            # Get the workflow
            workflow = session.query(WorkflowRun).filter_by(run_id=run_id, state='QUEUED').first()
            
            if not workflow:
                self.logger.warning(f"Workflow {run_id} not found or not in QUEUED state")
                return
            
            # Count running workflows
            running_count = session.query(WorkflowRun).filter(
                WorkflowRun.state.in_(['INITIALIZING', 'RUNNING', 'PAUSED'])
            ).count()
            
            # Check if we can process more workflows
            if running_count >= self.max_concurrent_workflows:
                self.logger.warning(
                    f"Already running {running_count} workflows, max is {self.max_concurrent_workflows}. "
                    f"Workflow {run_id} will be processed later."
                )
                return
            
            # Process the workflow
            try:
                self.process_workflow(session, workflow)
            except Exception as e:
                self.handle_error(session, workflow, e)
            
            session.commit()
        except SQLAlchemyError as e:
            self.logger.error(f"Database error processing workflow {run_id}: {e}")
            session.rollback()
        except Exception as e:
            self.logger.error(f"Error processing workflow {run_id}: {e}")
            self.logger.error(traceback.format_exc())
            session.rollback()
        finally:
            session.close()
    
    def poll_for_workflows(self):
        """Poll for new workflows to process (fallback mechanism)"""
        session = self.Session()
        try:
            # Count running workflows
            running_count = session.query(WorkflowRun).filter(
                WorkflowRun.state.in_(['INITIALIZING', 'RUNNING', 'PAUSED'])
            ).count()
            
            # Calculate how many new workflows we can process
            available_slots = max(0, self.max_concurrent_workflows - running_count)
            
            if available_slots <= 0:
                self.logger.debug(f"Already running {running_count} workflows, no slots available")
                return
            
            # Get queued workflows
            queued_workflows = session.query(WorkflowRun).filter_by(state='QUEUED').limit(available_slots).all()
            
            if queued_workflows:
                self.logger.info(f"Found {len(queued_workflows)} queued workflows")
                
                # Process each workflow
                for workflow in queued_workflows:
                    try:
                        self.process_workflow(session, workflow)
                    except Exception as e:
                        self.handle_error(session, workflow, e)
            
            session.commit()
        except SQLAlchemyError as e:
            self.logger.error(f"Database error polling for workflows: {e}")
            session.rollback()
        except Exception as e:
            self.logger.error(f"Error polling for workflows: {e}")
            self.logger.error(traceback.format_exc())
            session.rollback()
        finally:
            session.close()
    
    def process_workflow(self, session, workflow: WorkflowRun):
        """
        Process a workflow
        
        Args:
            session: The database session
            workflow: The workflow to process
        """
        self.logger.info(f"Processing workflow {workflow.run_id}")
        
        # Determine provider type from tags
        provider_type = None
        if workflow.tags and 'provider_type' in workflow.tags:
            provider_type = workflow.tags['provider_type']
        
        # If no provider type specified, use default
        if not provider_type:
            provider_type = 'sevenbridges'  # Default provider
            self.logger.info(f"No provider type specified for workflow {workflow.run_id}, using default: {provider_type}")
        
        # Get the provider
        try:
            provider = ProviderFactory.get_provider(provider_type)
        except ValueError as e:
            self.logger.error(f"Error getting provider for workflow {workflow.run_id}: {e}")
            workflow.state = 'SYSTEM_ERROR'
            return
        
        # Update workflow state
        workflow.state = 'INITIALIZING'
        session.commit()
        
        # Submit the workflow
        try:
            provider_id = provider.submit_workflow(workflow)
            
            # Update workflow with provider information
            workflow.tags = workflow.tags or {}
            workflow.tags['provider_type'] = provider_type
            workflow.tags['provider_id'] = provider_id
            workflow.state = 'RUNNING'
            
            self.logger.info(f"Workflow {workflow.run_id} submitted to {provider_type} with ID {provider_id}")
        except Exception as e:
            self.logger.error(f"Error submitting workflow {workflow.run_id}: {e}")
            self.logger.error(traceback.format_exc())
            workflow.state = 'SYSTEM_ERROR'
            workflow.tags = workflow.tags or {}
            workflow.tags['error'] = str(e)
            workflow.end_time = datetime.datetime.now(datetime.UTC)
    
    def check_workflow_status(self):
        """Check the status of running workflows"""
        session = self.Session()
        try:
            # Get running workflows
            running_workflows = session.query(WorkflowRun).filter(
                WorkflowRun.state.in_(['INITIALIZING', 'RUNNING', 'PAUSED'])
            ).all()
            
            if running_workflows:
                self.logger.info(f"Checking status of {len(running_workflows)} running workflows")
                
                # Check each workflow
                for workflow in running_workflows:
                    try:
                        self.update_workflow_status(session, workflow)
                    except Exception as e:
                        self.logger.error(f"Error checking status of workflow {workflow.run_id}: {e}")
                        self.logger.error(traceback.format_exc())
                        # Continue with next workflow
            
            session.commit()
        except SQLAlchemyError as e:
            self.logger.error(f"Database error checking workflow status: {e}")
            session.rollback()
        except Exception as e:
            self.logger.error(f"Error checking workflow status: {e}")
            self.logger.error(traceback.format_exc())
            session.rollback()
        finally:
            session.close()
    
    def update_workflow_status(self, session, workflow: WorkflowRun):
        """
        Update the status of a workflow
        
        Args:
            session: The database session
            workflow: The workflow to update
        """
        # Check if we need to update this workflow yet
        now = time.time()
        last_check = self.last_status_check.get(workflow.run_id, 0)
        if now - last_check < self.status_check_interval:
            return
        
        self.last_status_check[workflow.run_id] = now
        
        # Get provider information
        if not workflow.tags or 'provider_type' not in workflow.tags or 'provider_id' not in workflow.tags:
            self.logger.error(f"Workflow {workflow.run_id} missing provider information")
            return
        
        provider_type = workflow.tags['provider_type']
        provider_id = workflow.tags['provider_id']
        
        # Get the provider
        try:
            provider = ProviderFactory.get_provider(provider_type)
        except ValueError as e:
            self.logger.error(f"Error getting provider for workflow {workflow.run_id}: {e}")
            return
        
        # Get workflow status
        try:
            state, outputs, task_logs = provider.get_workflow_status(provider_id)
            
            # Update workflow state
            workflow.state = state
            
            # Update workflow end time if completed
            if state in ['COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']:
                workflow.end_time = datetime.datetime.now(datetime.UTC)
            
            # Update task logs
            self.update_task_logs(session, workflow, task_logs)
            
            # Update outputs
            if outputs:
                workflow.tags['outputs'] = outputs
            
            self.logger.info(f"Updated workflow {workflow.run_id} status to {state}")
        except Exception as e:
            self.logger.error(f"Error updating status of workflow {workflow.run_id}: {e}")
            self.logger.error(traceback.format_exc())
    
    def update_task_logs(self, session, workflow: WorkflowRun, task_logs: List[Dict[str, Any]]):
        """
        Update task logs for a workflow
        
        Args:
            session: The database session
            workflow: The workflow
            task_logs: The task logs from the provider
        """
        # Clear existing task logs
        session.query(TaskLog).filter_by(run_id=workflow.run_id).delete()
        
        # Add new task logs
        for i, log in enumerate(task_logs):
            task_id = log.get('id', str(uuid.uuid4()))
            
            task_log = TaskLog(
                id=task_id,
                run_id=workflow.run_id,
                name=log.get('name', f"Task {i}"),
                cmd=log.get('command', []),
                start_time=self._parse_datetime(log.get('start_time')),
                end_time=self._parse_datetime(log.get('end_time')),
                stdout=log.get('stdout'),
                stderr=log.get('stderr'),
                exit_code=log.get('exit_code')
            )
            session.add(task_log)
    
    def handle_error(self, session, workflow: WorkflowRun, error: Exception):
        """
        Handle an error processing a workflow
        
        Args:
            session: The database session
            workflow: The workflow
            error: The error
        """
        self.logger.error(f"Error processing workflow {workflow.run_id}: {error}")
        self.logger.error(traceback.format_exc())
        
        # Update workflow state
        workflow.state = 'SYSTEM_ERROR'
        
        # Add error to tags
        workflow.tags = workflow.tags or {}
        workflow.tags['error'] = str(error)
        
        # Set end time
        workflow.end_time = datetime.datetime.now(datetime.UTC)
    
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime.datetime]:
        """
        Parse a datetime string to a datetime object
        
        Args:
            dt_str: The datetime string
            
        Returns:
            datetime.datetime: The parsed datetime, or None if parsing fails
        """
        if not dt_str:
            return None
        
        try:
            # Try ISO format
            return datetime.datetime.fromisoformat(dt_str)
        except ValueError:
            try:
                # Try RFC 3339 format
                import dateutil.parser
                return dateutil.parser.parse(dt_str)
            except (ValueError, ImportError):
                self.logger.warning(f"Could not parse datetime: {dt_str}")
                return None