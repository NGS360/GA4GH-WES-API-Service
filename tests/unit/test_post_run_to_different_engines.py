import unittest
import json
from tests.test_base import BaseTestCase
from app.models.workflow import WorkflowRun
from app.extensions import DB

class TestPostRunToDifferentEngines(BaseTestCase):
    """Test that posting runs to different engines work """

    def setUp(self):
        """Set up test fixtures"""
        # Call parent setUp to set up Flask app, database and client
        super().setUp()
        # Create test workflow runs
        #self.create_test_runs(50)

    def test_post_run_with_no_engine_specified(self):
        """Test posting a run without specifying an engine"""
        response = self.client.post("/api/ga4gh/wes/v1/runs",
            json={
                'workflow_type': "CWL",
                'workflow_type_version': "1.0",
                'workflow_url': "hello_world.cwl",
                'workflow_params': {
                    "outputUri": "s3://my-test-bucket/outputs/"
                }
            }
        )
        # Assert the request failed because no engine was specified
        self.assertEqual(response.status_code, 400, "API request should have failed")


if __name__ == '__main__':
    unittest.main()