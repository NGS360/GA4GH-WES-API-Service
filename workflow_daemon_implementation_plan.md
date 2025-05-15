# Implementation Plan for WES Workflow Submission Daemon

## 1. Overview

We'll implement a daemon that:
- Runs as a separate process from the Flask application
- Polls the database for workflows in the "QUEUED" state
- Submits these workflows to either SevenBridges/Velsera or AWS HealthOmics
- Periodically polls the service providers to check workflow status
- Updates the workflow status in the database
- Logs errors and continues with the next workflow without retrying failed operations

## 2. Architecture

```mermaid
graph TD
    A[WES API Flask App] -->|Stores workflows| B[Database]
    C[Workflow Submission Daemon] -->|Polls for queued workflows| B
    C -->|Submits workflows| D[Provider Interface]
    D -->|Submits to| E[SevenBridges/Velsera API]
    D -->|Submits to| F[AWS HealthOmics API]
    C -->|Updates workflow status| B
```

## 3. Component Design

### 3.1 Core Daemon

```mermaid
classDiagram
    class WorkflowDaemon {
        +run()
        -poll_for_workflows()
        -process_workflow(workflow)
        -update_workflow_status()
        -handle_error(workflow, error)
    }
    
    class ProviderFactory {
        +get_provider(provider_type, config)
    }
    
    class WorkflowProviderInterface {
        <<interface>>
        +submit_workflow(workflow)
        +get_workflow_status(workflow_id)
        +cancel_workflow(workflow_id)
    }
    
    class SevenBridgesProvider {
        +submit_workflow(workflow)
        +get_workflow_status(workflow_id)
        +cancel_workflow(workflow_id)
    }
    
    class HealthOmicsProvider {
        +submit_workflow(workflow)
        +get_workflow_status(workflow_id)
        +cancel_workflow(workflow_id)
    }
    
    WorkflowDaemon --> ProviderFactory
    ProviderFactory --> WorkflowProviderInterface
    SevenBridgesProvider ..|> WorkflowProviderInterface
    HealthOmicsProvider ..|> WorkflowProviderInterface
```

### 3.2 Database Interaction

The daemon will use SQLAlchemy to interact with the same database as the Flask application. It will:
- Query for workflows in the "QUEUED" state
- Update workflow status as it changes
- Store provider-specific information (like provider workflow IDs) in the database

### 3.3 Provider Interface

We'll create a common interface for all workflow providers with methods for:
- Submitting workflows
- Checking workflow status
- Canceling workflows

Each provider implementation will handle the specifics of interacting with that provider's API.

## 4. Implementation Steps

### 4.1 Create Provider Interface and Implementations

1. Define a `WorkflowProviderInterface` abstract base class
2. Implement `SevenBridgesProvider` class
   - Add authentication using environment variables
   - Implement workflow submission
   - Implement status checking
   - Implement workflow cancellation
3. Implement `HealthOmicsProvider` class
   - Add authentication using environment variables
   - Implement workflow submission
   - Implement status checking
   - Implement workflow cancellation
4. Create a `ProviderFactory` to instantiate the appropriate provider

### 4.2 Implement Core Daemon

1. Create a `WorkflowDaemon` class
   - Implement polling for queued workflows
   - Implement workflow processing logic
   - Implement status update logic
   - Implement error handling
2. Create a main script to run the daemon
   - Parse command-line arguments
   - Configure logging
   - Initialize the daemon
   - Start the daemon process

### 4.3 Database Schema Updates

1. Add fields to the `WorkflowRun` model:
   - `provider_type`: The type of provider to use (e.g., "sevenbridges", "healthomics")
   - `provider_id`: The ID of the workflow in the provider's system
   - `provider_status`: The status of the workflow in the provider's system
   - `provider_metadata`: Additional provider-specific metadata

### 4.4 Configuration

1. Define environment variables for authentication:
   - `SEVENBRIDGES_API_TOKEN`: API token for SevenBridges/Velsera
   - `SEVENBRIDGES_API_ENDPOINT`: API endpoint URL for SevenBridges/Velsera
   - `AWS_ACCESS_KEY_ID`: AWS access key for HealthOmics
   - `AWS_SECRET_ACCESS_KEY`: AWS secret key for HealthOmics
   - `AWS_REGION`: AWS region for HealthOmics
2. Define daemon configuration:
   - `DAEMON_POLL_INTERVAL`: How often to poll for new workflows (in seconds)
   - `DAEMON_STATUS_CHECK_INTERVAL`: How often to check workflow status (in seconds)
   - `DAEMON_MAX_CONCURRENT_WORKFLOWS`: Maximum number of workflows to process concurrently

## 5. File Structure

```
scripts/
  workflow_daemon.py         # Main daemon script
  
app/
  daemon/
    __init__.py
    workflow_daemon.py       # Core daemon implementation
    providers/
      __init__.py
      provider_interface.py  # Abstract base class
      sevenbridges.py        # SevenBridges/Velsera implementation
      healthomics.py         # AWS HealthOmics implementation
      provider_factory.py    # Factory for creating providers
      
migrations/
  versions/
    xxxx_add_provider_fields.py  # Migration to add provider fields
```

## 6. Detailed Implementation

### 6.1 Provider Interface

```python
# app/daemon/providers/provider_interface.py
from abc import ABC, abstractmethod
from app.models.workflow import WorkflowRun

class WorkflowProviderInterface(ABC):
    """Interface for workflow execution providers"""
    
    @abstractmethod
    def submit_workflow(self, workflow: WorkflowRun) -> str:
        """
        Submit a workflow to the provider
        
        Args:
            workflow: The workflow run to submit
            
        Returns:
            str: The provider-specific workflow ID
        """
        pass
    
    @abstractmethod
    def get_workflow_status(self, provider_id: str) -> tuple:
        """
        Get the status of a workflow from the provider
        
        Args:
            provider_id: The provider-specific workflow ID
            
        Returns:
            tuple: (state, outputs, task_logs)
        """
        pass
    
    @abstractmethod
    def cancel_workflow(self, provider_id: str) -> bool:
        """
        Cancel a workflow
        
        Args:
            provider_id: The provider-specific workflow ID
            
        Returns:
            bool: True if cancellation was successful
        """
        pass
```

### 6.2 SevenBridges Provider

```python
# app/daemon/providers/sevenbridges.py
import os
import logging
from typing import Tuple, Dict, List, Any
from sevenbridges.api import Api
from app.models.workflow import WorkflowRun
from .provider_interface import WorkflowProviderInterface

class SevenBridgesProvider(WorkflowProviderInterface):
    """SevenBridges/Velsera workflow provider implementation"""
    
    def __init__(self):
        """Initialize the SevenBridges API client"""
        self.logger = logging.getLogger(__name__)
        
        # Get credentials from environment variables
        token = os.environ.get('SEVENBRIDGES_API_TOKEN')
        endpoint = os.environ.get('SEVENBRIDGES_API_ENDPOINT')
        
        if not token or not endpoint:
            raise ValueError("SEVENBRIDGES_API_TOKEN and SEVENBRIDGES_API_ENDPOINT must be set")
        
        self.api = Api(token=token, url=endpoint)
    
    def submit_workflow(self, workflow: WorkflowRun) -> str:
        """Submit a workflow to SevenBridges/Velsera"""
        self.logger.info(f"Submitting workflow {workflow.run_id} to SevenBridges")
        
        # Convert WES workflow to SevenBridges format
        task_inputs = self._convert_workflow_params(workflow.workflow_params)
        
        # Create and run the task
        task = self.api.tasks.create(
            name=f"WES-{workflow.run_id}",
            project=os.environ.get('SEVENBRIDGES_PROJECT'),
            app=workflow.workflow_url,
            inputs=task_inputs,
            description=f"Workflow run {workflow.run_id}"
        )
        
        self.logger.info(f"Submitted workflow {workflow.run_id} to SevenBridges with ID {task.id}")
        return task.id
    
    def get_workflow_status(self, provider_id: str) -> Tuple[str, Dict, List[Dict]]:
        """Get the status of a workflow from SevenBridges/Velsera"""
        self.logger.debug(f"Checking status of SevenBridges task {provider_id}")
        
        task = self.api.tasks.get(provider_id)
        
        # Map SevenBridges status to WES status
        status_map = {
            'DRAFT': 'INITIALIZING',
            'QUEUED': 'QUEUED',
            'RUNNING': 'RUNNING',
            'COMPLETED': 'COMPLETE',
            'FAILED': 'EXECUTOR_ERROR',
            'ABORTED': 'CANCELED'
        }
        
        wes_status = status_map.get(task.status, 'UNKNOWN')
        
        # Get outputs if the task is completed
        outputs = {}
        if task.status == 'COMPLETED':
            outputs = {k: v for k, v in task.outputs.items()}
        
        # Get task logs
        task_logs = []
        if hasattr(task, 'execution_status') and task.execution_status:
            for job in task.execution_status.jobs:
                task_logs.append({
                    'name': job.name,
                    'start_time': job.start_time,
                    'end_time': job.end_time,
                    'status': job.status,
                    'command': job.command
                })
        
        return wes_status, outputs, task_logs
    
    def cancel_workflow(self, provider_id: str) -> bool:
        """Cancel a workflow in SevenBridges/Velsera"""
        self.logger.info(f"Canceling SevenBridges task {provider_id}")
        
        try:
            task = self.api.tasks.get(provider_id)
            task.abort()
            return True
        except Exception as e:
            self.logger.error(f"Error canceling task {provider_id}: {e}")
            return False
    
    def _convert_workflow_params(self, params: Dict) -> Dict[str, Any]:
        """Convert WES workflow parameters to SevenBridges format"""
        # This is a simplified implementation
        # In a real implementation, this would handle file references, etc.
        return params
```

### 6.3 AWS HealthOmics Provider

```python
# app/daemon/providers/healthomics.py
import os
import logging
import boto3
from typing import Tuple, Dict, List
from app.models.workflow import WorkflowRun
from .provider_interface import WorkflowProviderInterface

class HealthOmicsProvider(WorkflowProviderInterface):
    """AWS HealthOmics workflow provider implementation"""
    
    def __init__(self):
        """Initialize the AWS HealthOmics client"""
        self.logger = logging.getLogger(__name__)
        
        # AWS credentials are expected to be in the environment
        # or in the AWS credentials file
        region = os.environ.get('AWS_REGION', 'us-east-1')
        self.client = boto3.client('omics', region_name=region)
    
    def submit_workflow(self, workflow: WorkflowRun) -> str:
        """Submit a workflow to AWS HealthOmics"""
        self.logger.info(f"Submitting workflow {workflow.run_id} to AWS HealthOmics")
        
        # Convert WES workflow to HealthOmics format
        run_params = self._convert_workflow_params(workflow.workflow_params)
        
        # Create and start the workflow run
        response = self.client.start_run(
            workflowId=workflow.workflow_url,  # This would be the workflow ID in HealthOmics
            name=f"WES-{workflow.run_id}",
            parameters=run_params,
            tags={
                'WES-RunId': workflow.run_id
            }
        )
        
        self.logger.info(f"Submitted workflow {workflow.run_id} to HealthOmics with ID {response['id']}")
        return response['id']
    
    def get_workflow_status(self, provider_id: str) -> Tuple[str, Dict, List[Dict]]:
        """Get the status of a workflow from AWS HealthOmics"""
        self.logger.debug(f"Checking status of HealthOmics run {provider_id}")
        
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
        if 'tasks' in response:
            for task in response['tasks']:
                task_logs.append({
                    'name': task['name'],
                    'start_time': task.get('startTime'),
                    'end_time': task.get('stopTime'),
                    'status': task['status'],
                    'log_uri': task.get('logUri')
                })
        
        return wes_status, outputs, task_logs
    
    def cancel_workflow(self, provider_id: str) -> bool:
        """Cancel a workflow in AWS HealthOmics"""
        self.logger.info(f"Canceling HealthOmics run {provider_id}")
        
        try:
            self.client.cancel_run(id=provider_id)
            return True
        except Exception as e:
            self.logger.error(f"Error canceling run {provider_id}: {e}")
            return False
    
    def _convert_workflow_params(self, params: Dict) -> Dict:
        """Convert WES workflow parameters to HealthOmics format"""
        # This is a simplified implementation
        # In a real implementation, this would handle file references, etc.
        return params
```

### 6.4 Provider Factory

```python
# app/daemon/providers/provider_factory.py
from .provider_interface import WorkflowProviderInterface
from .sevenbridges import SevenBridgesProvider
from .healthomics import HealthOmicsProvider

class ProviderFactory:
    """Factory for creating workflow providers"""
    
    @staticmethod
    def get_provider(provider_type: str) -> WorkflowProviderInterface:
        """
        Get a workflow provider by type
        
        Args:
            provider_type: The type of provider to create
            
        Returns:
            WorkflowProviderInterface: The provider instance
            
        Raises:
            ValueError: If the provider type is not supported
        """
        if provider_type == 'sevenbridges':
            return SevenBridgesProvider()
        elif provider_type == 'healthomics':
            return HealthOmicsProvider()
        else:
            raise ValueError(f"Unsupported provider type: {provider_type}")
```

### 6.5 Core Daemon Implementation

```python
# app/daemon/workflow_daemon.py
import os
import time
import logging
import datetime
import traceback
from typing import List
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.workflow import WorkflowRun, TaskLog
from app.daemon.providers.provider_factory import ProviderFactory

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
        self.Session = sessionmaker(bind=self.engine)
        
        # Configuration
        self.poll_interval = int(os.environ.get('DAEMON_POLL_INTERVAL', '60'))
        self.status_check_interval = int(os.environ.get('DAEMON_STATUS_CHECK_INTERVAL', '300'))
        self.max_concurrent_workflows = int(os.environ.get('DAEMON_MAX_CONCURRENT_WORKFLOWS', '10'))
        
        # Track when we last checked each workflow's status
        self.last_status_check = {}
    
    def run(self):
        """Run the daemon"""
        self.logger.info("Starting workflow daemon")
        
        while True:
            try:
                # Poll for new workflows
                self.poll_for_workflows()
                
                # Check status of running workflows
                self.check_workflow_status()
                
                # Sleep before next poll
                time.sleep(self.poll_interval)
            except Exception as e:
                self.logger.error(f"Error in daemon main loop: {e}")
                self.logger.error(traceback.format_exc())
                # Continue running despite errors
    
    def poll_for_workflows(self):
        """Poll for new workflows to process"""
        session = self.Session()
        try:
            # Get queued workflows
            queued_workflows = session.query(WorkflowRun).filter_by(state='QUEUED').all()
            
            if queued_workflows:
                self.logger.info(f"Found {len(queued_workflows)} queued workflows")
                
                # Process each workflow
                for workflow in queued_workflows:
                    try:
                        self.process_workflow(session, workflow)
                    except Exception as e:
                        self.handle_error(session, workflow, e)
            
            session.commit()
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
        
        # Determine provider type
        provider_type = workflow.tags.get('provider_type', 'sevenbridges') if workflow.tags else 'sevenbridges'
        
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
    
    def update_task_logs(self, session, workflow: WorkflowRun, task_logs: List[dict]):
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
            task_log = TaskLog(
                id=f"{workflow.run_id}-{i}",
                run_id=workflow.run_id,
                name=log.get('name', f"Task {i}"),
                cmd=log.get('command', []),
                start_time=log.get('start_time'),
                end_time=log.get('end_time'),
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
```

### 6.6 Main Daemon Script

```python
# scripts/workflow_daemon.py
#!/usr/bin/env python3
import os
import sys
import time
import logging
import argparse
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.daemon.workflow_daemon import WorkflowDaemon

def setup_logging(log_level):
    """Set up logging configuration"""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='WES Workflow Submission Daemon')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the logging level')
    parser.add_argument('--db-uri', help='Database URI (overrides environment variable)')
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Set up logging
    setup_logging(args.log_level)
    
    # Get database URI
    db_uri = args.db_uri or os.environ.get('DATABASE_URI')
    if not db_uri:
        logging.error("Database URI not provided. Use --db-uri or set DATABASE_URI environment variable.")
        sys.exit(1)
    
    # Create and run the daemon
    daemon = WorkflowDaemon(db_uri)
    daemon.run()

if __name__ == '__main__':
    main()
```

## 7. Deployment and Operation

### 7.1 Environment Setup

1. Set up environment variables:
   ```
   # Database
   DATABASE_URI=postgresql://user:password@localhost/wes
   
   # SevenBridges/Velsera
   SEVENBRIDGES_API_TOKEN=your-token
   SEVENBRIDGES_API_ENDPOINT=https://api.sbgenomics.com/v2
   SEVENBRIDGES_PROJECT=your-project-id
   
   # AWS HealthOmics
   AWS_ACCESS_KEY_ID=your-access-key
   AWS_SECRET_ACCESS_KEY=your-secret-key
   AWS_REGION=us-east-1
   
   # Daemon Configuration
   DAEMON_POLL_INTERVAL=60
   DAEMON_STATUS_CHECK_INTERVAL=300
   DAEMON_MAX_CONCURRENT_WORKFLOWS=10
   ```

### 7.2 Running the Daemon

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

2. Run the daemon:
   ```
   python scripts/workflow_daemon.py
   ```

3. For production, use a process manager like Supervisor or systemd to ensure the daemon stays running.

### 7.3 Monitoring and Logging

1. The daemon logs to stdout/stderr, which can be captured by the process manager
2. Consider adding metrics collection for:
   - Number of workflows processed
   - Success/failure rates
   - Processing time

## 8. Testing Strategy

1. Unit tests for each provider implementation
2. Integration tests with mock API responses
3. End-to-end tests with real API calls (using test accounts)
4. Test cases for error handling and recovery

## 9. Future Enhancements

1. Support for additional providers (Arvados)
2. Webhook support for status updates
3. Improved error handling and retry mechanisms
4. Performance optimizations for handling large numbers of workflows
5. Support for workflow versioning and provenance tracking