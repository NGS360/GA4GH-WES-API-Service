from tests.test_base import BaseTestCase
import unittest

class TestWebEndpoints(BaseTestCase):
    """ Test the web endpoints of the application """
    def setUp(self):
        """Set up test fixtures"""
        # Call parent setUp to set up Flask app, database and client
        super().setUp()

    def test_index(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200, "Feetching index page failed")

    def test_runs(self):
        response = self.client.get("/runs")
        self.assertEqual(response.status_code, 200, "Feetching runs page failed")

    def test_run(self):
        # Create test workflow runs
        runs = self.create_test_runs(1)
        run_id = runs[0].run_id
        response = self.client.get(f"/runs/{run_id}")
        self.assertEqual(response.status_code, 200, "Feetching run page failed")

if __name__ == "__main__":
    unittest.main()
