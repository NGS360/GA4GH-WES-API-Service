import os
import json
import unittest
import time
from pathlib import Path
from tests.wes_client import WesClient
from tests.test_base import BaseTestCase
from app.models.workflow import WorkflowRun
from app.extensions import DB

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
        
        # Step 3: Simulate the workflow executor processing the request
        with self.app.app_context():
            # Get the workflow from the database
            workflow = WorkflowRun.query.get(run_id)
            self.assertIsNotNone(workflow, "Workflow not found in database")
            self.assertEqual(workflow.state, 'QUEUED', "Workflow state should be QUEUED")
            self.assertFalse(workflow.processed, "Workflow should not be processed yet")
            
            # Simulate processing by the workflow executor
            workflow.processed = True
            workflow.processed_at = time.time()
            workflow.external_id = f"test-external-{run_id}"
            DB.session.commit()
            
            # Simulate workflow completion
            workflow.state = 'COMPLETE'
            workflow.end_time = time.time()
            DB.session.commit()
        
        # Step 4: Check status until completion (should be immediate since we manually set it)
        try:
            final_status = self.wes_client.get_run_status(run_id)
            print(f"Final status: {json.dumps(final_status, indent=2)}")
            
            # Step 5: Get detailed run log
            run_log = self.wes_client.get_run_log(run_id)
            print(f"Run log: {json.dumps(run_log, indent=2)}")
            
            # Step 6: Verify the run completed successfully
            self.assertEqual(final_status['state'], 'COMPLETE',
                           f"Workflow failed with state: {final_status['state']}")
            
        except Exception as e:
            # Cancel the run if there's an error
            self.wes_client.cancel_run(run_id)
            raise e
    
    def test_workflow_cancellation(self):
        """Test cancelling a workflow"""
        # Submit a workflow
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
        
        run_id = response['run_id']
        print(f"Submitted workflow with run_id: {run_id}")
        
        # Cancel the workflow
        cancel_response = self.wes_client.cancel_run(run_id)
        self.assertEqual(cancel_response['run_id'], run_id, "Cancel response should include run_id")
        
        # Check that the workflow is cancelled
        with self.app.app_context():
            workflow = WorkflowRun.query.get(run_id)
            self.assertEqual(workflow.state, 'CANCELED', "Workflow state should be CANCELED")

if __name__ == '__main__':
    unittest.main()
