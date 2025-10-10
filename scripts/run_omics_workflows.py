#!/usr/bin/env python3
"""
Script for running multiple workflows in AWS Omics through the WES API.

Usage:
    python run_omics_workflows.py --workflow-id wf-12345abcdef --input-files s3://bucket/file1.fastq s3://bucket/file2.fastq
"""

import argparse
import json
import os
import sys
from typing import List
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.wes_client import WESClient


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Run multiple workflows in AWS Omics through WES API")
    
    # WES API connection parameters
    parser.add_argument("--wes-url", default="http://localhost:8000/ga4gh/wes/v1",
                      help="WES API URL (default: http://localhost:8000/ga4gh/wes/v1)")
    parser.add_argument("--username", default=os.environ.get("WES_USERNAME"),
                      help="WES API username (default: from WES_USERNAME env var)")
    parser.add_argument("--password", default=os.environ.get("WES_PASSWORD"),
                      help="WES API password (default: from WES_PASSWORD env var)")
    
    # Workflow parameters
    parser.add_argument("--workflow-id", required=True,
                      help="AWS Omics workflow ID")
    parser.add_argument("--workflow-type", default="WDL",
                      help="Workflow type (default: WDL)")
    parser.add_argument("--workflow-version", default="1.0",
                      help="Workflow type version (default: 1.0)")
    parser.add_argument("--input-files", required=True, nargs='+',
                      help="List of input files (S3 paths)")
    parser.add_argument("--input-param-name", default="input_file",
                      help="Name of the input file parameter in the workflow (default: input_file)")
    parser.add_argument("--additional-params", default="{}",
                      help="Additional workflow parameters as JSON string (default: {})")
    
    # Execution options
    parser.add_argument("--monitor", action="store_true",
                      help="Monitor workflow execution after submission")
    parser.add_argument("--poll-interval", type=int, default=30,
                      help="Polling interval in seconds when monitoring (default: 30)")
    
    return parser.parse_args()


def submit_workflows(client: WESClient, workflow_id: str, workflow_type: str, 
                   workflow_version: str, input_files: List[str], 
                   input_param_name: str, additional_params: dict) -> List[str]:
    """
    Submit multiple workflows to WES API.
    
    Args:
        client: WES API client
        workflow_id: AWS Omics workflow ID
        workflow_type: Workflow type (WDL, CWL)
        workflow_version: Workflow type version
        input_files: List of input file paths
        input_param_name: Name of the input file parameter
        additional_params: Additional workflow parameters
        
    Returns:
        List of run IDs
    """
    run_ids = []
    
    for input_file in input_files:
        # Prepare workflow parameters
        params = additional_params.copy()
        params[input_param_name] = input_file
        
        # Prepare workflow URL with omics prefix
        workflow_url = f"omics:{workflow_id}"
        
        print(f"Submitting workflow with input: {input_file}")
        
        # Submit workflow
        run_id = client.submit_workflow(
            workflow_type=workflow_type,
            workflow_type_version=workflow_version,
            workflow_url=workflow_url,
            workflow_params=params
        )
        
        run_ids.append(run_id)
        print(f"Submitted workflow run: {run_id}")
    
    return run_ids


def monitor_workflows(client: WESClient, run_ids: List[str], poll_interval: int):
    """
    Monitor workflows until completion.
    
    Args:
        client: WES API client
        run_ids: List of run IDs to monitor
        poll_interval: Polling interval in seconds
    """
    completed = set()
    status_map = {}
    
    print("\nMonitoring workflow runs:")
    
    while len(completed) < len(run_ids):
        for run_id in run_ids:
            if run_id in completed:
                continue
                
            status_response = client.get_run_status(run_id)
            current_status = status_response.get('state', 'UNKNOWN')
            
            # Print status update if changed
            if status_map.get(run_id) != current_status:
                print(f"Run {run_id}: {current_status}")
                status_map[run_id] = current_status
            
            # Check if run is in a terminal state
            if current_status in ('COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED'):
                completed.add(run_id)
        
        if len(completed) < len(run_ids):
            time.sleep(poll_interval)
    
    # Print final summary
    print("\nAll workflows completed:")
    for run_id in run_ids:
        status = client.get_run_status(run_id).get('state', 'UNKNOWN')
        print(f"Run {run_id}: {status}")


def main():
    """Main entry point."""
    args = parse_args()
    
    # Validate inputs
    if not args.username or not args.password:
        print("Error: WES API username and password are required.", file=sys.stderr)
        print("Set them using --username/--password or WES_USERNAME/WES_PASSWORD environment variables.", file=sys.stderr)
        sys.exit(1)
    
    # Parse additional parameters
    try:
        additional_params = json.loads(args.additional_params)
    except json.JSONDecodeError:
        print(f"Error: Could not parse additional parameters as JSON: {args.additional_params}", file=sys.stderr)
        sys.exit(1)
    
    # Create WES client
    client = WESClient(url=args.wes_url, username=args.username, password=args.password)
    
    # Submit workflows
    run_ids = submit_workflows(
        client=client,
        workflow_id=args.workflow_id,
        workflow_type=args.workflow_type,
        workflow_version=args.workflow_version,
        input_files=args.input_files,
        input_param_name=args.input_param_name,
        additional_params=additional_params
    )
    
    print(f"\nSubmitted {len(run_ids)} workflows")
    
    # Monitor workflows if requested
    if args.monitor and run_ids:
        monitor_workflows(client, run_ids, args.poll_interval)


if __name__ == "__main__":
    main()