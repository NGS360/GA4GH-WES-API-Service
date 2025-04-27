import unittest
from app import create_app
from app.extensions import DB
from config import TestConfig

class BaseTestCase(unittest.TestCase):
    """Base test case for all tests"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = create_app(TestConfig)

        # Create the database and load test data
        self.app_context = self.app.app_context()
        self.app_context.push()

        DB.create_all()

        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up after test"""
        # Close and remove the temporary database
        self.client = None

        DB.drop_all()
        DB.session.remove()

        self.app_context.pop()

        self.app = None
