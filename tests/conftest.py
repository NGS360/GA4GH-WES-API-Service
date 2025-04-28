import os
import pytest
import tempfile
from flask import Flask
from app import create_app
from app.extensions import DB

@pytest.fixture
def app():
    """Create and configure a Flask app for testing"""
    # Create a temporary file to use as a test database
    db_fd, db_path = tempfile.mkstemp()
    
    app = create_app({
        'TESTING': True,
        'DATABASE_URL': f'sqlite:///{db_path}',
        'WES_PROVIDER': 'aws-omics',  # Can be overridden by environment variable
    })
    
    # Create the database and load test data
    with app.app_context():
        DB.create_all()
    
    yield app
    
    # Close and remove the temporary database
    os.close(db_fd)
    os.unlink(db_path)

@pytest.fixture
def client(app):
    """A test client for the app"""
    return app.test_client()