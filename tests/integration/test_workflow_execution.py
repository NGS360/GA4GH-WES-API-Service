import os
import json
import pytest
import time
from pathlib import Path
from tests.wes_client import WesClient

@pytest.fixture
def wes_client():
    """Create a WES client for testing"""
    # Use environment variable or default to localhost
    base_url = os.environ.get('WES_API_URL', 'http://localhost:5000/api/ga4gh/wes/v1')
    return WesClient(base_url)

@pytest.fixture
def hello_world_workflow():
    """Get the path to the hello world workflow"""
    workflow_path = Path(__file__).parent.parent / 'workflows' / 'hello_world.cwl'
    assert workflow_path.exists(), f"Workflow file not found at {workflow_path}"
    return str(workflow_path)

def test_workflow_execution(wes_client, hello_world_workflow):
    """Test the full workflow execution lifecycle"""
    
    # Step 1: Check service info
    service_info = wes_client.get_service_info()
    print(f"Service info: {json.dumps(service_info, indent=2)}")
    
    # Verify service supports CWL
    assert 'CWL' in service_info.get('workflow_type_versions', {}), "Service does not support CWL"
    
    # Step 2: Submit workflow
    with open(hello_world_workflow, 'r') as f:
        workflow_content = f.read()
    
    workflow_params = {
        "outputUri": "s3://my-test-bucket/outputs/"
    }
    
    # Convert to JSON string as required by the API
    workflow_params_str = json.dumps(workflow_params)
    
    # Submit the workflow
    response = wes_client.run_workflow(
        workflow_params=workflow_params_str,
        workflow_type="CWL",
        workflow_type_version="1.0",
        workflow_url="hello_world.cwl",
        workflow_attachment=[("hello_world.cwl", workflow_content, "application/text")]
    )
    
    assert 'run_id' in response, "No run_id in response"
    run_id = response['run_id']
    print(f"Submitted workflow with run_id: {run_id}")
    
    # Step 3: Check status until completion
    try:
        final_status = wes_client.wait_for_run_completion(run_id, timeout=300)
        print(f"Final status: {json.dumps(final_status, indent=2)}")
        
        # Step 4: Get detailed run log
        run_log = wes_client.get_run_log(run_id)
        print(f"Run log: {json.dumps(run_log, indent=2)}")
        
        # Step 5: Verify the run completed successfully
        assert final_status['state'] == 'COMPLETE', f"Workflow failed with state: {final_status['state']}"
        
    except TimeoutError as e:
        # Cancel the run if it times out
        wes_client.cancel_run(run_id)
        raise e
