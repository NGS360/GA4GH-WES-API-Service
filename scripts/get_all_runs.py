#!/usr/bin/env python3
"""
Script to sync AWS Omics runs with the local database.
This script will:
1. Fetch all runs from AWS Omics
2. Update or create database records for each run
3. Optionally delete old runs from AWS Omics
"""
import os
import sys
import boto3
import datetime
from datetime import datetime as dt

# Add the parent directory to the path so we can import from the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import DB
from app.models.workflow import WorkflowRun
from app.services.aws_omics import HealthOmicsService

# Create the Flask app
app = create_app()
app.app_context().push()

# Initialize the AWS Omics service
omics_service = HealthOmicsService()

def sync_runs():
    """Sync AWS Omics runs with the local database"""
    total_runs = 0
    next_token = None
    updated_runs = 0
    new_runs = 0

    now = dt.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=10)
    runs_to_delete = []

    print("Starting sync of AWS Omics runs with local database...")

    while True:
        # Get runs from AWS Omics
        if next_token:
            response = omics_service.list_runs(next_token=next_token)
        else:
            response = omics_service.list_runs()

        for run in response.get('items', []):
            total_runs += 1
            run_id = run.get('id')
            
            # Check if the run exists in the database
            db_run = WorkflowRun.query.get(run_id)
            
            if db_run:
                # Update existing run
                db_run.state = omics_service.map_run_state(run.get('status'))
                db_run.arn = run.get('arn')
                db_run.workflow_id = run.get('workflowId')
                db_run.name = run.get('name', f"run-{run_id}")
                db_run.priority = run.get('priority')
                db_run.storage_capacity = run.get('storageCapacity')
                try:
                    # Print the actual format of the times
                    if run.get('creationTime'):
                        print(f"Creation time format for run {run_id}: {run.get('creationTime')} (type: {type(run.get('creationTime'))})")
                        if isinstance(run.get('creationTime'), str):
                            if 'Z' in run.get('creationTime'):
                                db_run.creation_time = dt.fromisoformat(run.get('creationTime').replace('Z', '+00:00'))
                            else:
                                db_run.creation_time = dt.fromisoformat(run.get('creationTime'))
                        else:
                            db_run.creation_time = run.get('creationTime')
                            
                    if run.get('startTime'):
                        if isinstance(run.get('startTime'), str):
                            if 'Z' in run.get('startTime'):
                                db_run.start_time = dt.fromisoformat(run.get('startTime').replace('Z', '+00:00'))
                            else:
                                db_run.start_time = dt.fromisoformat(run.get('startTime'))
                        else:
                            db_run.start_time = run.get('startTime')
                            
                    if run.get('stopTime'):
                        if isinstance(run.get('stopTime'), str):
                            if 'Z' in run.get('stopTime'):
                                db_run.stop_time = dt.fromisoformat(run.get('stopTime').replace('Z', '+00:00'))
                            else:
                                db_run.stop_time = dt.fromisoformat(run.get('stopTime'))
                        else:
                            db_run.stop_time = run.get('stopTime')
                except (ValueError, TypeError) as e:
                    print(f"Error parsing dates for run {run_id}: {str(e)}")
                db_run.storage_type = run.get('storageType')
                updated_runs += 1
            else:
                # Get detailed run information
                try:
                    run_details = omics_service.get_run(run_id)
                    
                    # Create new run record
                    new_run = WorkflowRun(
                        run_id=run_id,
                        name=run.get('name', f"run-{run_id}"),
                        state=omics_service.map_run_state(run.get('status')),
                        arn=run.get('arn'),
                        workflow_id=run.get('workflowId'),
                        priority=run.get('priority'),
                        storage_capacity=run.get('storageCapacity'),
                        creation_time=dt.fromisoformat(run.get('creationTime').replace('Z', '+00:00')) if run.get('creationTime') and isinstance(run.get('creationTime'), str) and 'Z' in run.get('creationTime')
                                     else dt.fromisoformat(run.get('creationTime')) if run.get('creationTime') and isinstance(run.get('creationTime'), str)
                                     else run.get('creationTime') if run.get('creationTime')
                                     else None,
                        start_time=dt.fromisoformat(run.get('startTime').replace('Z', '+00:00')) if run.get('startTime') and isinstance(run.get('startTime'), str) and 'Z' in run.get('startTime')
                                  else dt.fromisoformat(run.get('startTime')) if run.get('startTime') and isinstance(run.get('startTime'), str)
                                  else run.get('startTime') if run.get('startTime')
                                  else None,
                        stop_time=dt.fromisoformat(run.get('stopTime').replace('Z', '+00:00')) if run.get('stopTime') and isinstance(run.get('stopTime'), str) and 'Z' in run.get('stopTime')
                                 else dt.fromisoformat(run.get('stopTime')) if run.get('stopTime') and isinstance(run.get('stopTime'), str)
                                 else run.get('stopTime') if run.get('stopTime')
                                 else None,
                        storage_type=run.get('storageType'),
                        # Set other fields from run_details
                        workflow_type=run_details.get('workflowType', 'unknown'),
                        workflow_type_version=run_details.get('workflowTypeVersion', '1.0'),
                        workflow_url=run_details.get('workflowId', ''),
                        workflow_params=run_details.get('parameters', {}),
                        workflow_engine='aws-omics',
                        tags=run_details.get('tags', {})
                    )
                    DB.session.add(new_run)
                    new_runs += 1
                except Exception as e:
                    print(f"Error getting details for run {run_id}: {str(e)}")

            # Decide if we want to delete the run from AWS Omics
            status = run.get('status')
            created = run.get("creationTime")
            if status in ["COMPLETED", "FAILED", "CANCELLED"] and created:
                try:
                    # Print the actual format of the creation time
                    print(f"Creation time format for run {run_id}: {created} (type: {type(created)})")
                    
                    # Handle different date formats
                    if isinstance(created, str):
                        if 'Z' in created:
                            created_date = dt.fromisoformat(created.replace('Z', '+00:00'))
                        else:
                            created_date = dt.fromisoformat(created)
                    else:
                        # If it's already a datetime object
                        created_date = created
                        
                    if created_date < cutoff:
                        runs_to_delete.append(run_id)
                except (ValueError, TypeError) as e:
                    print(f"Error parsing creation time for run {run_id}: {str(e)}")

        # Commit the changes to the database
        DB.session.commit()
        
        next_token = response.get('nextToken')
        if not next_token:
            break

    print(f"Sync complete. Total runs: {total_runs}, Updated: {updated_runs}, New: {new_runs}")
    
    # Delete old runs if needed
    if runs_to_delete:
        delete_runs = input("Do you want to delete these runs from AWS Omics? (y/n): ")
        print(f"Runs to delete: {len(runs_to_delete)}")
        # Do not delete runs while we are testing.
        #if delete_runs.lower() == 'y':
        #    for run_id in runs_to_delete:
        #        try:
        #            omics_service.client.delete_run(id=run_id)
        #            print(f"Deleted run {run_id}")
        #        except Exception as e:
        #            print(f"Error deleting run {run_id}: {str(e)}")

if __name__ == "__main__":
    sync_runs()
