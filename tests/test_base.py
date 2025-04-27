import os
import unittest
import tempfile
from flask import Flask
from app import create_app
from app.extensions import DB
from config import TestConfig

class BaseTestCase(unittest.TestCase):
    """Base test case for all tests"""
    
    def setUp(self):
        """Set up test environment"""
        # Create a temporary file to use as a test database
        #self.db_fd, self.db_path = tempfile.mkstemp()

        self.app = create_app(TestConfig)
        #{
        #    'TESTING': True,
        #    'DATABASE_URL': f'sqlite:///{self.db_path}'
            #'WES_PROVIDER': 'aws-omics',  # Can be overridden by environment variable
        #})

        # Create the database and load test data
        with self.app.app_context():
            DB.create_all()

        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up after test"""
        # Close and remove the temporary database
        #os.close(self.db_fd)
        #os.unlink(self.db_path)
