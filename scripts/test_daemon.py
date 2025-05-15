#!/usr/bin/env python3
"""
Test script for the workflow submission daemon
"""
import os
import sys
import time
import logging
import argparse
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.daemon.workflow_daemon import WorkflowDaemon
from app.models.workflow import WorkflowRun
from app.extensions import DB
from app import create_app


def setup_logging(log_level):
    """Set up logging configuration"""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )


def create_test_workflow(provider_type):
    """
    Create a test workflow in the database
    
    Args:
        provider_type: The provider type to use
        
    Returns:
        str: The run ID of the created workflow
    """
    # Create a test workflow
    workflow = WorkflowRun(
        run_id='test-' + str(int(time.time())),
        state='QUEUED',
        workflow_type='CWL',
        workflow_type_version='v1.0',
        workflow_url='hello_world.cwl',  # This should be a valid workflow ID or URL for your provider
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
    
    logging.info(f"Created test workflow with run_id {workflow.run_id}")
    return workflow.run_id


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Test the WES Workflow Submission Daemon')
    parser.add_argument('--log-level', default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the logging level')
    parser.add_argument('--provider', default='sevenbridges',
                        choices=['sevenbridges', 'healthomics'],
                        help='The provider to test')
    parser.add_argument('--create-workflow', action='store_true',
                        help='Create a test workflow in the database')
    parser.add_argument('--run-daemon', action='store_true',
                        help='Run the daemon for a short time')
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Set up logging
    setup_logging(args.log_level)
    
    # Create Flask app to initialize database connection
    app = create_app()
    
    with app.app_context():
        # Create a test workflow if requested
        if args.create_workflow:
            run_id = create_test_workflow(args.provider)
            logging.info(f"Created test workflow with run_id {run_id}")
        
        # Run the daemon for a short time if requested
        if args.run_daemon:
            # Get database URI from app config
            db_uri = app.config['SQLALCHEMY_DATABASE_URI']
            
            # Create daemon
            daemon = WorkflowDaemon(db_uri)
            
            # Set short poll interval for testing
            daemon.poll_interval = 5
            
            # Run daemon in a separate thread for a short time
            import threading
            import time
            
            def run_daemon():
                daemon.run()
            
            thread = threading.Thread(target=run_daemon)
            thread.daemon = True
            thread.start()
            
            logging.info("Daemon started in background thread")
            logging.info("Running for 30 seconds...")
            
            # Wait for a short time
            time.sleep(30)
            
            # Stop daemon
            daemon.stop()
            thread.join(timeout=5)
            
            logging.info("Daemon stopped")


if __name__ == '__main__':
    main()