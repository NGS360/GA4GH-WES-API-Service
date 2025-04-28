# Example Workflow Execution

## 1. Understanding the Current System

The current system:
- Uses AWS HealthOmics service for workflow execution
- Implements the GA4GH WES API
- Has a web UI for viewing and managing workflow runs
- Does not show an example workflow execution with a test script
- Currently, the API directly uses WesFactory to create a WesService to run workflows

The expected future state:

- Has an example workflow execution test script that shows:
  a. Workflow submission
  b. Workflow status checking until completion or failure
- Example execution is agnostic of healthomics or another service
- The REST API logs workflow requests in a database
- A separate service monitors the database and runs the workflows

## 2. Implementation Plan

### 2.1 Update Workflow Run Model

Enhance the WorkflowRun model to include additional fields for tracking execution status:

```python
class WorkflowRun(DB.Model):
    """Workflow run model"""
    __tablename__ = 'workflow_runs'

    run_id = DB.Column(DB.String(36), primary_key=True)
    name = DB.Column(DB.String(200), nullable=False)
    state = DB.Column(DB.String(20), nullable=False)
    workflow_params = DB.Column(DB.JSON)
    workflow_type = DB.Column(DB.String(50), nullable=False)
    workflow_type_version = DB.Column(DB.String(20), nullable=False)
    workflow_engine = DB.Column(DB.String(50))
    workflow_engine_version = DB.Column(DB.String(20))
    workflow_url = DB.Column(DB.String(500), nullable=False)
    tags = DB.Column(DB.JSON)
    start_time = DB.Column(DB.DateTime)
    end_time = DB.Column(DB.DateTime)
    
    # New fields
    submitted_at = DB.Column(DB.DateTime)
    processed_at = DB.Column(DB.DateTime)
    processed = DB.Column(DB.Boolean, default=False)
    external_id = DB.Column(DB.String(100))  # ID from external system (e.g., AWS HealthOmics)
    error_message = DB.Column(DB.Text)
```

### 2.2 Modify API to Log Requests Only

Update the WES API to only log workflow requests to the database without directly executing them:

```python
@api.route('/runs')
class WorkflowRuns(Resource):
    @api.doc('list_runs')
    def get(self):
        """List workflow runs"""
        try:
            # Query the database instead of calling the service directly
            runs_query = WorkflowRunModel.query.all()
            runs = []
            for run in runs_query:
                runs.append({
                    'run_id': run.run_id,
                    'state': run.state
                })
            return {
                'runs': runs,
                'next_page_token': ''  # Implement pagination as needed
            }
        except Exception as e:
            current_app.logger.error(f"Failed to list runs: {str(e)}")
            api.abort(500, f"Failed to list runs: {str(e)}")

    @api.doc('run_workflow')
    @api.expect(run_request)
    def post(self):
        """Run a workflow"""
        try:
            workflow_params = api.payload.get('workflow_params', {})
            tags = api.payload.get('tags', {})

            # Generate a unique run ID
            import uuid
            run_id = str(uuid.uuid4())

            # Create local record without starting the actual workflow
            new_run = WorkflowRunModel(
                run_id=run_id,
                name=api.payload.get('workflow_url', '').split('/')[-1],
                state='QUEUED',
                workflow_type=api.payload['workflow_type'],
                workflow_type_version=api.payload['workflow_type_version'],
                workflow_url=api.payload['workflow_url'],
                workflow_params=workflow_params,
                workflow_engine=api.payload.get('workflow_engine', 'aws-omics'),
                workflow_engine_version=api.payload.get('workflow_engine_version'),
                tags=tags,
                submitted_at=datetime.utcnow(),
                processed=False
            )
            DB.session.add(new_run)
            DB.session.commit()

            return {'run_id': run_id}
        except Exception as e:
            current_app.logger.error(f"Failed to queue workflow: {str(e)}")
            api.abort(500, f"Failed to queue workflow: {str(e)}")
```

### 2.3 Create Workflow Execution Service

Create a separate service that monitors the database for new workflow requests and executes them:

```python
# app/services/workflow_executor.py

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
```

### 2.4 Create Command-Line Script for Executor Service

Create a command-line script to run the workflow executor service:

```python
# scripts/run_workflow_executor.py

#!/usr/bin/env python3
import os
import sys
import logging
from flask import Flask
from app import create_app
from app.services.workflow_executor import WorkflowExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Create Flask app with application context
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        # Get poll interval from environment or use default
        poll_interval = int(os.environ.get('WORKFLOW_POLL_INTERVAL', '10'))
        
        # Create and start the workflow executor
        executor = WorkflowExecutor(poll_interval=poll_interval)
        executor.start()
```

### 2.5 Update API Status Endpoints

Update the API status endpoints to read from the database instead of directly calling the service:

```python
@api.route('/runs/<string:run_id>/status')
class WorkflowRunStatus(Resource):
    def get(self, run_id):
        """Get run status"""
        try:
            # Query the database for the workflow
            workflow = WorkflowRunModel.query.get(run_id)
            
            if not workflow:
                api.abort(404, f"Workflow run {run_id} not found")
                
            return {
                'run_id': run_id,
                'state': workflow.state
            }
        except Exception as e:
            current_app.logger.error(f"Failed to get run status {run_id}: {str(e)}")
            api.abort(500, f"Failed to get run status {run_id}: {str(e)}")
```

### 2.6 Create a Test Client for the New Architecture

Create a unittest-based test client that demonstrates the workflow execution lifecycle:

```python
# tests/integration/test_workflow_execution.py

import os
import json
import unittest
import time
from pathlib import Path
from tests.wes_client import WesClient
from tests.test_base import BaseTestCase

class TestWorkflowExecution(BaseTestCase):
    """Test the workflow execution lifecycle"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Call parent setUp to set up Flask app and database
        super().setUp()
        
        # Create WES client
        base_url = os.environ.get('WES_API_URL', 'http://localhost:5000/api/ga4gh/wes/v1')
        self.wes_client = WesClient(base_url)
        
        # Get path to hello world workflow
        workflow_path = Path(__file__).parent.parent / 'workflows' / 'hello_world.cwl'
        self.assertTrue(workflow_path.exists(), f"Workflow file not found at {workflow_path}")
        self.hello_world_workflow = str(workflow_path)
    
    def test_workflow_execution(self):
        """Test the full workflow execution lifecycle"""
        
        # Step 1: Check service info
        service_info = self.wes_client.get_service_info()
        print(f"Service info: {json.dumps(service_info, indent=2)}")
        
        # Verify service supports CWL
        self.assertIn('CWL', service_info.get('workflow_type_versions', {}), 
                     "Service does not support CWL")
        
        # Step 2: Submit workflow
        with open(self.hello_world_workflow, 'r') as f:
            workflow_content = f.read()
        
        workflow_params = {
            "outputUri": "s3://my-test-bucket/outputs/"
        }
        
        # Convert to JSON string as required by the API
        workflow_params_str = json.dumps(workflow_params)
        
        # Submit the workflow
        response = self.wes_client.run_workflow(
            workflow_params=workflow_params_str,
            workflow_type="CWL",
            workflow_type_version="1.0",
            workflow_url="hello_world.cwl",
            workflow_attachment=[("hello_world.cwl", workflow_content, "application/text")]
        )
        
        self.assertIn('run_id', response, "No run_id in response")
        run_id = response['run_id']
        print(f"Submitted workflow with run_id: {run_id}")
        
        # Step 3: Check status until completion
        try:
            final_status = self.wes_client.wait_for_run_completion(run_id, timeout=300)
            print(f"Final status: {json.dumps(final_status, indent=2)}")
            
            # Step 4: Get detailed run log
            run_log = self.wes_client.get_run_log(run_id)
            print(f"Run log: {json.dumps(run_log, indent=2)}")
            
            # Step 5: Verify the run completed successfully
            self.assertEqual(final_status['state'], 'COMPLETE', 
                           f"Workflow failed with state: {final_status['state']}")
            
        except TimeoutError as e:
            # Cancel the run if it times out
            self.wes_client.cancel_run(run_id)
            raise e

if __name__ == '__main__':
    unittest.main()
```

## 3. Running the Example

To run the example workflow execution:

1. Start the Flask application:
   ```bash
   python application.py
   ```

2. In a separate terminal, start the workflow executor service:
   ```bash
   python scripts/run_workflow_executor.py
   ```

3. Run the integration test:
   ```bash
   python tests/integration/test_workflow_execution.py
   ```

## 4. Database Migration

Create a migration to add the new fields to the WorkflowRun model:

```bash
flask db migrate -m "Add workflow execution tracking fields"
flask db upgrade
```

## 5. Future Enhancements

