#!/usr/bin/env python3
"""
Script to create test workflow runs in the database.
This will help us test the pagination functionality.
"""

import datetime
import uuid
import sys
from app import create_app
from app.models.workflow import WorkflowRun
from app.extensions import DB

def create_test_runs(count=100):
    """Create test workflow runs in the database"""
    print(f"Creating {count} test workflow runs...")
    
    app = create_app()
    with app.app_context():
        # Check if we already have runs
        existing_count = WorkflowRun.query.count()
        if existing_count > 0:
            print(f"Database already has {existing_count} runs. Skipping creation.")
            return
        
        # Create test runs
        states = ['QUEUED', 'INITIALIZING', 'RUNNING', 'COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']
        workflow_types = ['CWL', 'WDL']
        
        for i in range(count):
            # Calculate dates with some variation
            start_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=i % 30, hours=i % 24)
            
            # Some runs are completed, some are still running
            end_time = None
            state = states[i % len(states)]
            if state in ['COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']:
                end_time = start_time + datetime.timedelta(hours=2, minutes=(i % 60))
            
            # Create run with unique ID
            run_id = str(uuid.uuid4())
            workflow_type = workflow_types[i % len(workflow_types)]
            
            new_run = WorkflowRun(
                run_id=run_id,
                state=state,
                workflow_type=workflow_type,
                workflow_type_version='1.0',
                workflow_url=f'https://example.com/workflows/workflow_{i}.{workflow_type.lower()}',
                workflow_params={'input': f'test_input_{i}'},
                workflow_engine='test_engine',
                workflow_engine_version='1.0',
                tags={'test': 'true', 'index': i},
                start_time=start_time,
                end_time=end_time
            )
            
            DB.session.add(new_run)
            
            # Commit in batches to avoid memory issues
            if (i + 1) % 10 == 0:
                print(f"Added {i + 1} runs...")
                DB.session.commit()
        
        # Final commit for any remaining runs
        DB.session.commit()
        print(f"Successfully created {count} test workflow runs.")

if __name__ == "__main__":
    count = 100
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except ValueError:
            print(f"Invalid count: {sys.argv[1]}. Using default: 100")
    
    create_test_runs(count)