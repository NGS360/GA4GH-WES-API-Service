#!/usr/bin/env python3
"""
Script to run the workflow executor service.
This service monitors the database for new workflow requests and executes them.
"""
import os
import sys
import logging
from flask import Flask
from app import create_app
from app.services.workflow_executor import WorkflowExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Create Flask app with application context
app = create_app()

if __name__ == '__main__':
    with app.app_context():
        # Get poll interval from environment or use default
        poll_interval = int(os.environ.get('WORKFLOW_POLL_INTERVAL', '10'))
        
        # Create and start the workflow executor
        executor = WorkflowExecutor(poll_interval=poll_interval)
        executor.start()