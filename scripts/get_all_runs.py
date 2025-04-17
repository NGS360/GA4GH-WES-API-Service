#!/usr/bin/env python3
"""
Script to sync AWS Omics runs with the local database.
This script will:
1. Read runs from a JSON file if provided
2. Or fetch all runs from AWS Omics if no file is provided
3. Update or create database records for each run
4. Optionally delete old runs from AWS Omics
"""
import os
import sys
import boto3
import json
import argparse
import datetime
import ast
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

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Sync AWS Omics runs with the local database')
    parser.add_argument('--file', '-f', type=str, help='Path to JSON file containing run data')
    return parser.parse_args()

def load_runs_from_file(file_path):
    """Load runs from a JSON file"""
    runs = []
    try:
        import re
        from datetime import datetime, timezone
        
        with open(file_path, 'r') as f:
            content = f.read()
            # Handle the case where each line is a separate Python dict object
            for line in content.strip().split('\n'):
                try:
                    # Replace datetime objects with ISO format strings
                    # Pattern to match datetime.datetime(...) objects
                    pattern = r'datetime\.datetime\((\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)(?:,\s*\d+)?,\s*tzinfo=tzutc\(\)\)'
                    
                    # Replace datetime objects with ISO format strings
                    def replace_datetime(match):
                        year, month, day, hour, minute, second = map(int, match.groups())
                        dt_obj = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
                        return f'"{dt_obj.isoformat()}"'
                    
                    # Replace datetime objects with ISO strings
                    line_with_iso = re.sub(pattern, replace_datetime, line)
                    
                    # Replace Python dict syntax with JSON syntax
                    line_with_iso = line_with_iso.replace("'", '"')
                    
                    # Parse as JSON
                    import json
                    run_dict = json.loads(line_with_iso)
                    
                    # Convert ISO strings back to datetime objects
                    for key in ['creationTime', 'startTime', 'stopTime']:
                        if key in run_dict and isinstance(run_dict[key], str):
                            run_dict[key] = datetime.fromisoformat(run_dict[key])
                    
                    runs.append(run_dict)
                except Exception as e:
                    print(f"Error parsing line: {line[:50]}... - {str(e)}")
        
        print(f"Loaded {len(runs)} runs from {file_path}")
        return runs
    except Exception as e:
        print(f"Error loading runs from file {file_path}: {str(e)}")
        return []

def sync_runs(runs_from_file=None):
    """Sync AWS Omics runs with the local database"""
    total_runs = 0
    next_token = None
    updated_runs = 0
    new_runs = 0

    now = dt.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=10)
    runs_to_delete = []

    print("Starting sync of runs with local database...")

    # Process runs from file if provided
    if runs_from_file:
        runs_to_process = runs_from_file
        print(f"Processing {len(runs_to_process)} runs from file...")
    else:
        # Otherwise fetch runs from AWS Omics
        print("No file provided. Fetching runs from AWS Omics...")
        runs_to_process = []
        while True:
            # Get runs from AWS Omics
            if next_token:
                response = omics_service.list_runs(next_token=next_token)
            else:
                response = omics_service.list_runs()
            
            runs_to_process.extend(response.get('items', []))
            
            next_token = response.get('nextToken')
            if not next_token:
                break
        
        print(f"Fetched {len(runs_to_process)} runs from AWS Omics")

    # Process all runs
    for run in runs_to_process:
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
                # Handle datetime fields
                if run.get('creationTime'):
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
            # Get detailed run information if needed
            run_details = {}
            if not runs_from_file:
                try:
                    run_details = omics_service.get_run(run_id)
                except Exception as e:
                    print(f"Error getting details for run {run_id}: {str(e)}")
            
            try:
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
                print(f"Error creating database record for run {run_id}: {str(e)}")

        # Decide if we want to delete the run from AWS Omics
        if not runs_from_file:  # Only consider deletion for runs from AWS Omics
            status = run.get('status')
            created = run.get("creationTime")
            if status in ["COMPLETED", "FAILED", "CANCELLED"] and created:
                try:
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
    args = parse_arguments()
    
    runs_from_file = None
    if args.file:
        runs_from_file = load_runs_from_file(args.file)
    
    sync_runs(runs_from_file)
