import os
import json
import unittest
import time
import datetime
from pathlib import Path
from tests.test_base import BaseTestCase
from app.models.workflow import WorkflowRun
from app.extensions import DB

class TestWorkflowExecution(BaseTestCase):
    """Test the workflow execution lifecycle"""

    def setUp(self):
        """Set up test fixtures"""
        # Call parent setUp to set up Flask app, database and client
        super().setUp()

        # Get path to hello world workflow
        workflow_path = Path(__file__).parent.parent / 'workflows' / 'hello_world.cwl'
        self.assertTrue(workflow_path.exists(), f"Workflow file not found at {workflow_path}")
        self.hello_world_workflow = str(workflow_path)

    def test_workflow_execution(self):
        """Test the full workflow execution lifecycle"""

        # Step 1: Check service info
        service_info = self.client.get("/ga4gh/wes/v1/service-info")

        # Verify service supports CWL
        self.assertIn('CWL', service_info.json.get('workflow_type_versions', {}),
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
        response = self.client.post("/ga4gh/wes/v1/runs",
            json={
                'workflow_params': workflow_params_str,
                'workflow_type': "CWL",
                'workflow_type_version': "1.0",
                'workflow_url': "hello_world.cwl",
                'workflow_attachment': [("hello_world.cwl", workflow_content, "application/text")]
            }
        )

        self.assertIn('run_id', response.json, "No run_id in response")
        run_id = response.json['run_id']

        # Step 3: Simulate the workflow executor processing the request
        workflow = DB.session.query(WorkflowRun).filter_by(run_id=run_id).first()
        self.assertIsNotNone(workflow, "Workflow not found in database")
        self.assertEqual(workflow.state, 'QUEUED', "Workflow state should be QUEUED")

        # Simulate workflow completion
        workflow.state = 'COMPLETE'
        workflow.end_time = datetime.datetime.now()
        DB.session.commit()

        # Step 4: Check status until completion (should be immediate since we manually set it)
        final_status = self.client.get(f"/ga4gh/wes/v1/runs/{run_id}/status")

        # Step 5: Get detailed run log
        run_log = self.client.get(f"/ga4gh/wes/v1/runs/{run_id}")

        # Step 6: Verify the run completed successfully
        self.assertEqual(final_status.json['state'], 'COMPLETE',
                        f"Workflow failed with state: {final_status.json['state']}")

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
        response = self.client.post(
            '/ga4gh/wes/v1/runs',
            json={
                "workflow_params": workflow_params_str,
                "workflow_type": "CWL",
                "workflow_type_version": "1.0",
                "workflow_url": "hello_world.cwl",
                "workflow_attachment": [("hello_world.cwl", workflow_content, "application/text")]
            }
        )
        self.assertEqual(response.status_code, 200, "Workflow submission failed")
        run_id = response.json['run_id']

        # Cancel the workflow
        cancel_response = self.client.post(f'/ga4gh/wes/v1/runs/{run_id}/cancel')
        self.assertEqual(cancel_response.json['run_id'], run_id, "Cancel response should include run_id")

        # Check that the workflow is cancelled
        workflow = DB.session.query(WorkflowRun).filter_by(run_id=run_id).first()
        self.assertEqual(workflow.state, 'CANCELED', "Workflow state should be CANCELED")

if __name__ == '__main__':
    unittest.main()
