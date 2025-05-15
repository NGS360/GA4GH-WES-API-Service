#!/usr/bin/env python3
"""
Test script for the workflow daemon notification API
"""
import os
import sys
import argparse
import json
import uuid
import requests
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.models.workflow import WorkflowRun
from app.extensions import DB


def create_test_workflow(provider_type):
    """
    Create a test workflow in the database
    
    Args:
        provider_type: The provider type to use
        
    Returns:
        str: The run ID of the created workflow
    """
    # Create Flask app to initialize database connection
    app = create_app()
    
    with app.app_context():
        # Create a test workflow
        workflow = WorkflowRun(
            run_id='test-' + str(uuid.uuid4()),
            state='QUEUED',
            workflow_type='CWL',
            workflow_type_version='v1.0',
            workflow_url=get_test_workflow_url(provider_type),
            workflow_params={
                'input': 'Hello, World!'
            },
            tags={
                'provider_type': provider_type,
                'test': 'true'
            }
        )
        
        # Add to database
        DB.session.add(workflow)
        DB.session.commit()
        
        print(f"Created test workflow with run_id {workflow.run_id}")
        return workflow.run_id


def get_test_workflow_url(provider_type):
    """
    Get a test workflow URL for the specified provider
    
    Args:
        provider_type: The provider type
        
    Returns:
        str: A test workflow URL
    """
    if provider_type == 'sevenbridges':
        # Use a public SB app if available, otherwise a URL
        return os.environ.get('TEST_SB_APP_ID', 'https://example.com/workflow.cwl')
    elif provider_type == 'healthomics':
        # Use a test workflow ID if available, otherwise a URL
        return os.environ.get('TEST_HEALTHOMICS_WORKFLOW_ID', 'https://example.com/workflow.wdl')
    elif provider_type == 'arvados':
        # Use a test collection if available, otherwise a URL
        return os.environ.get('TEST_ARVADOS_WORKFLOW', 'https://example.com/workflow.cwl')
    else:
        return 'https://example.com/workflow.cwl'


def notify_daemon(run_id, host, port):
    """
    Notify the daemon about a workflow
    
    Args:
        run_id: The workflow run ID
        host: The notification server host
        port: The notification server port
        
    Returns:
        bool: True if notification was successful
    """
    url = f"http://{host}:{port}"
    payload = {"run_id": run_id}
    
    print(f"Sending notification to {url}")
    print(f"Payload: {json.dumps(payload)}")
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        print(f"Response status code: {response.status_code}")
        print(f"Response body: {response.text}")
        
        return response.status_code == 200
    except requests.RequestException as e:
        print(f"Error: {e}")
        return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Test the workflow daemon notification API')
    parser.add_argument('--host', default='localhost',
                        help='Notification server host')
    parser.add_argument('--port', type=int, default=5001,
                        help='Notification server port')
    parser.add_argument('--run-id',
                        help='Workflow run ID to notify about (if not provided, a new workflow will be created)')
    parser.add_argument('--provider', default='sevenbridges',
                        choices=['sevenbridges', 'healthomics', 'arvados'],
                        help='Provider type for new workflow')
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Get or create run ID
    run_id = args.run_id
    if not run_id:
        run_id = create_test_workflow(args.provider)
    
    # Notify daemon
    success = notify_daemon(run_id, args.host, args.port)
    
    if success:
        print("Notification successful!")
        sys.exit(0)
    else:
        print("Notification failed!")
        sys.exit(1)


if __name__ == '__main__':
    main()