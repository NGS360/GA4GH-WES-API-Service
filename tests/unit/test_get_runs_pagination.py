import unittest
import json
from tests.test_base import BaseTestCase
from app.models.workflow import WorkflowRun
from app.extensions import DB

class TestGetRunsPagination(BaseTestCase):
    """Test the pagination functionality of the WorkflowRuns().get() method"""

    def setUp(self):
        """Set up test fixtures"""
        # Call parent setUp to set up Flask app, database and client
        super().setUp()
        # Create test workflow runs
        self.create_test_runs(50)

    def test_default_pagination(self):
        """Test default pagination (no parameters)"""
        response = self.client.get("/api/ga4gh/wes/v1/runs")
        self.assertEqual(response.status_code, 200, "API request failed")
        
        data = json.loads(response.data)
        self.assertIn('runs', data, "Response missing 'runs' key")
        self.assertIn('next_page_token', data, "Response missing 'next_page_token' key")
        
        # Default page size is 50, so we should get all 50 runs with no next page
        self.assertEqual(len(data['runs']), 50, "Expected 50 runs in default pagination")
        self.assertEqual(data['next_page_token'], '', "Expected empty next_page_token for default pagination")
        
        # Verify run structure (RunSummary format)
        for run in data['runs']:
            self.assertIn('run_id', run, "Run missing 'run_id'")
            self.assertIn('state', run, "Run missing 'state'")
            self.assertIn('start_time', run, "Run missing 'start_time'")
            self.assertIn('end_time', run, "Run missing 'end_time'")
            self.assertIn('tags', run, "Run missing 'tags'")

    def test_custom_page_size(self):
        """Test custom page size"""
        response = self.client.get("/api/ga4gh/wes/v1/runs?page_size=10")
        self.assertEqual(response.status_code, 200, "API request failed")
        
        data = json.loads(response.data)
        self.assertIn('runs', data, "Response missing 'runs' key")
        self.assertIn('next_page_token', data, "Response missing 'next_page_token' key")
        
        # We requested 10 runs per page, so we should get 10 runs
        self.assertEqual(len(data['runs']), 10, "Expected 10 runs with page_size=10")
        self.assertEqual(data['next_page_token'], '10', "Expected next_page_token='10'")

    def test_page_navigation(self):
        """Test navigation through pages"""
        page_size = 5
        page_token = '0'
        
        # Test first page
        response = self.client.get(f"/api/ga4gh/wes/v1/runs?page_size={page_size}&page_token={page_token}")
        self.assertEqual(response.status_code, 200, "API request failed")
        
        data = json.loads(response.data)
        self.assertEqual(len(data['runs']), page_size, f"Expected {page_size} runs on first page")
        self.assertEqual(data['next_page_token'], '5', "Expected next_page_token='5'")
        
        # Test second page
        page_token = data['next_page_token']
        response = self.client.get(f"/api/ga4gh/wes/v1/runs?page_size={page_size}&page_token={page_token}")
        self.assertEqual(response.status_code, 200, "API request failed")
        
        data = json.loads(response.data)
        self.assertEqual(len(data['runs']), page_size, f"Expected {page_size} runs on second page")
        self.assertEqual(data['next_page_token'], '10', "Expected next_page_token='10'")
        
        # Verify runs on second page are different from first page
        first_page_response = self.client.get(f"/api/ga4gh/wes/v1/runs?page_size={page_size}&page_token=0")
        first_page_data = json.loads(first_page_response.data)
        
        first_page_run_ids = [run['run_id'] for run in first_page_data['runs']]
        second_page_run_ids = [run['run_id'] for run in data['runs']]
        
        # Check that there's no overlap between pages
        self.assertEqual(len(set(first_page_run_ids).intersection(set(second_page_run_ids))), 0,
                         "Expected no overlap between pages")

    def test_invalid_page_token(self):
        """Test invalid page_token"""
        response = self.client.get("/api/ga4gh/wes/v1/runs?page_token=invalid")
        self.assertEqual(response.status_code, 400, "Expected 400 status code for invalid page_token")
        
        data = json.loads(response.data)
        self.assertIn('msg', data, "Response missing 'msg' key")
        self.assertEqual(data['msg'], 'Invalid page_token', "Expected error message about invalid page_token")
        self.assertEqual(data['status_code'], 400, "Expected status_code=400 in response")

    def test_empty_result_set(self):
        """Test pagination with empty result set"""
        # Clear all runs
        DB.session.query(WorkflowRun).delete()
        DB.session.commit()
        
        response = self.client.get("/api/ga4gh/wes/v1/runs")
        self.assertEqual(response.status_code, 200, "API request failed")
        
        data = json.loads(response.data)
        self.assertEqual(len(data['runs']), 0, "Expected 0 runs in empty result set")
        self.assertEqual(data['next_page_token'], '', "Expected empty next_page_token for empty result set")

if __name__ == '__main__':
    unittest.main()