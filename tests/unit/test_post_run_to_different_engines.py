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

    def test_post_run_to_arvados(self):
        """Test posting a run to Arvados"""
        response = self.client.post("/api/ga4gh/wes/v1/runs",
            json={
                'workflow_type': "CWL",
                'workflow_type_version': "1.0",
                'workflow_engine': "Arvados",
                'workflow_url': "arvados://xngs1-abcde-zxcvbnm1234qwert",
                'workflow_params': {
                    "string_input": "This is a basic string input",
                    "file_input": "xngs1-file-id",
                }
            }
        )
        # Assert the request was successful
        self.assertEqual(response.status_code, 200, "API request should have succeeded")
    
    def test_post_run_to_awshealthomics(self):
        """Test posting a run to AWS Health Omics"""
        response = self.client.post("/api/ga4gh/wes/v1/runs",
            json={
                'workflow_type': "CWL",
                'workflow_type_version': "1.0",
                'workflow_engine': "AWSHealthOmics",
                'workflow_url': "omics://workflow/abcdef1234567890",
                'workflow_params': {
                    "string_input": "This is a basic string input",
                    "file_input": "s3://my-test-bucket/file.txt",
                }
            }
        )
        # Assert the request was successful
        self.assertEqual(response.status_code, 200, "API request should have succeeded")

    def test_post_run_to_sevenbridges(self):
        """Test posting a run to Seven Bridges"""
        response = self.client.post("/api/ga4gh/wes/v1/runs",
            json={
                'workflow_type': "CWL",
                'workflow_type_version': "1.0",
                'workflow_engine': "SevenBridges",
                'workflow_url': "sevenbridges://org_uuid/project_uuid/workflow_uuid",
                'workflow_params': {
                    "string_input": "This is a basic string input",
                    "file_input": "sevenbridges://file_uuid",
                }
            }
        )
        # Assert the request was successful
        self.assertEqual(response.status_code, 200, "API request should have succeeded")

if __name__ == '__main__':
    unittest.main()