#!/usr/bin/env python
import argparse
import logging
import requests
import time
import os
import json
from pathlib import Path

class WesClient:
    """
    A service-agnostic client for interacting with WES API implementations.
    """
    def __init__(self, base_url=None):
        """
        Initialize the WES client with a base URL.
        """
        self.base_url = base_url

    def get_service_info(self):
        """Get information about the WES service"""
        response = requests.get(f"{self.base_url}/service-info")
        response.raise_for_status()
        return response.json()

    def list_runs(self):
        """List all workflow runs"""
        response = requests.get(f"{self.base_url}/runs")
        response.raise_for_status()
        return response.json()

    def run_workflow(self, workflow_params, workflow_type, workflow_type_version, 
                    workflow_url, tags=None, workflow_engine=None, 
                    workflow_engine_version=None, workflow_engine_parameters=None,
                    workflow_attachment=None):
        """Submit a new workflow run"""
        data = {
            'workflow_params': workflow_params,
            'workflow_type': workflow_type,
            'workflow_type_version': workflow_type_version,
            'workflow_url': workflow_url
        }

        if tags:
            data['tags'] = tags
        if workflow_engine:
            data['workflow_engine'] = workflow_engine
        if workflow_engine_version:
            data['workflow_engine_version'] = workflow_engine_version
        if workflow_engine_parameters:
            data['workflow_engine_parameters'] = workflow_engine_parameters

        files = {}
        if workflow_attachment:
            for i, attachment in enumerate(workflow_attachment):
                files[f'workflow_attachment[{i}]'] = attachment

        if files:
            response = requests.post(f"{self.base_url}/runs", data=data, files=files)
        else:
            response = requests.post(f"{self.base_url}/runs", json=data)

        response.raise_for_status()
        return response.json()

    def get_run_status(self, run_id):
        """Get the status of a workflow run"""
        response = requests.get(f"{self.base_url}/runs/{run_id}/status")
        response.raise_for_status()
        return response.json()

    def get_run_log(self, run_id):
        """Get detailed information about a workflow run"""
        response = requests.get(f"{self.base_url}/runs/{run_id}")
        response.raise_for_status()
        return response.json()

    def cancel_run(self, run_id):
        """Cancel a workflow run"""
        response = requests.post(f"{self.base_url}/runs/{run_id}/cancel")
        response.raise_for_status()
        return response.json()

    def wait_for_run_completion(self, run_id, timeout=300, poll_interval=5):
        """
        Wait for a workflow run to complete, with timeout.
        
        Args:
            run_id: The ID of the workflow run
            timeout: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
            
        Returns:
            The final run status
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_run_status(run_id)
            state = status.get('state')

            # Check if the run has completed (successfully or not)
            if state in ['COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']:
                return status

            # Wait before checking again
            time.sleep(poll_interval)

        raise TimeoutError(f"Workflow run {run_id} did not complete within {timeout} seconds")

if __name__ == "__main__":
    # Example usage
    parser = argparse.ArgumentParser(description="WES Client Example")
    parser.add_argument('--base-url', type=str, help='Base URL of the WES service', default='http://localhost:5000/api/ga4gh/wes/v1')
    parser.add_argument('--engine', choices=["cwltool", "Arvados", "SevenBridges", "Omics"], help='Workflow engine to use', default='cwltool')
    parser.add_argument('--workflow-url', type=str, help='URL of the workflow to run', required=True)
    parser.add_argument('--tags', type=str, help='Tags for the workflow run (JSON format)', default='{}')
    parser.add_argument('--wait', action='store_true', default=False, help='Wait for the workflow to complete')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    logging.info("WES Client Example")
    logging.info("Arguments: %s", args)

    client = WesClient(base_url=args.base_url)

    logging.info("Getting service info...")
    print(client.get_service_info())

    # List all runs
    logging.info("Listing all runs...")
    print(client.list_runs())

    # Submit a workflow
    logging.info("Submitting workflow...")
    
    # For cwltool, the workflow file would need tobe read and sent as a file attachment
    workflow_engine = args.engine
    workflow_attachment = None
    
    if workflow_engine == "cwltool":
        with open(args.workflow_url, 'r') as f:
            workflow_content = f.read()
        workflow_attachment = [(os.path.basename(args.workflow_url), workflow_content, "application/text")]

        workflow_url = os.path.basename(args.workflow_url)
    else:
        workflow_url = args.workflow_url
        tags = args.tags

    workflow_params = {
    }

    response = requests.post(
        f"{client.base_url}/runs",
        json={
            'workflow_params': workflow_params,
            'workflow_type': "CWL",
            'workflow_type_version': "1.0",
            'workflow_engine': workflow_engine,
            'workflow_url': workflow_url,
            'workflow_attachment': workflow_attachment
        }
    )
    if response.status_code != 200:
        print("Workflow submission failed: ", response.text)
        exit(1)
    run_id = response.json()['run_id']
    print(f"Workflow submitted: {run_id}")

    #response = client.run_workflow(
    #    workflow_params=workflow_params_str,
    #    workflow_type='CWL',
    #    workflow_type_version="1.0",
    #    workflow_url="hello_world.cwl",
    #    workflow_attachment=workflow_attachment
    #)
    #print("Workflow submitted:", response)
    #run_id = response['run_id']

    if args.wait:
        print("Waiting for workflow to complete...")
        try:
            final_status = client.wait_for_run_completion(run_id, timeout=600)
            print("Workflow completed:", final_status)
        except TimeoutError as e:
            print(e)
            # Optionally cancel the run if it times out
            client.cancel_run(run_id)
            print("Workflow run canceled.")
        else:
            # Get the final log
            log = client.get_run_log(run_id)
            print("Final workflow log:", log)
