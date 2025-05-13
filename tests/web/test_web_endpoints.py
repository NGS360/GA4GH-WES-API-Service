from tests.test_base import BaseTestCase

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
