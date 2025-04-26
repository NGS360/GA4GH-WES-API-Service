# Example Workflow Execution

## 1. Understanding the Current System

The current system:
- Uses AWS HealthOmics service for workflow execution
- Implements the GA4GH WES API
- Has a web UI for viewing and managing workflow runs
- Does not show an example workflow execution with a test script

The expected future state:

- Has an example workflow execution test script that shows:
  a. Workflow submission
  b. Workflow status checking until completion or failure
- Example execution is agnostic of healthomics or another service

## 2. Implementation Plan

### 2.1 Create Test Directory Structure

Create a new `tests` directory in the project root with the following structure:

```
tests/
├── __init__.py
├── conftest.py                # Pytest configuration and fixtures
├── integration/               # Integration tests
│   ├── __init__.py
│   └── test_workflow_execution.py  # Our example workflow test
└── workflows/                 # Test workflow definitions
    └── hello_world.cwl        # Simple "Hello World" workflow
```

### 2.2 Create Service-Agnostic API Client

Create an abstract API client that can work with any WES implementation:

```python
# tests/wes_client.py
import requests
import time
import os

class WesClient:
    """
    A service-agnostic client for interacting with WES API implementations.
    """
    def __init__(self, base_url=None):
        """
        Initialize the WES client with a base URL.
        If not provided, uses the environment variable WES_API_URL.
        """
        self.base_url = base_url or os.environ.get('WES_API_URL', 'http://localhost:5000/api/ga4gh/wes/v1')
        
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
```

### 2.3 Create a Simple Test Workflow

Create a simple "Hello World" workflow in CWL format:

```yaml
# tests/workflows/hello_world.cwl

cwlVersion: v1.0
class: Workflow
inputs: []
outputs:
  output_file:
    type: File
    outputSource: say_hello/output_file

steps:
  say_hello:
    run:
      class: CommandLineTool
      baseCommand: [echo, "Hello, World!"]
      stdout: hello.txt
      inputs: []
      outputs:
        output_file:
          type: stdout
    in: []
    out: [output_file]

requirements:
  DockerRequirement:
    dockerPull: ubuntu:latest
```

### 2.4 Implement Integration Test

Create a pytest-based integration test that demonstrates workflow execution:

```python
# tests/integration/test_workflow_execution.py

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
```

### 2.5 Make API Service-Agnostic

To make the API service-agnostic, we need to abstract the service provider implementation. This involves:

1. Creating a service provider interface
2. Implementing the interface for AWS HealthOmics
3. Adding configuration-based selection of the service provider

#### Service Provider Interface

```python
# app/services/wes_provider.py

from abc import ABC, abstractmethod

class WesProvider(ABC):
    """Abstract base class for WES providers"""
    
    @abstractmethod
    def start_run(self, workflow_id, role_arn, parameters=None, output_uri=None, tags=None):
        """Start a workflow run"""
        pass
    
    @abstractmethod
    def get_run(self, run_id):
        """Get run details"""
        pass
    
    @abstractmethod
    def list_runs(self, next_token=None, max_results=100):
        """List workflow runs"""
        pass
    
    @abstractmethod
    def cancel_run(self, run_id):
        """Cancel a workflow run"""
        pass
    
    @abstractmethod
    def map_run_state(self, provider_status):
        """Map provider-specific status to WES state"""
        pass
```

#### Update AWS HealthOmics Service

Update the existing AWS HealthOmics service to implement the WesProvider interface:

```python
# app/services/aws_omics.py

from app.services.wes_provider import WesProvider

class HealthOmicsService(WesProvider):
    """AWS HealthOmics Service implementation of WesProvider"""
    # Existing implementation with WesProvider interface
```

#### Factory for Service Selection

Create a factory to select the appropriate service provider:

```python
# app/services/wes_factory.py

from app.services.aws_omics import HealthOmicsService
# Import other providers as they are implemented

class WesFactory:
    """Factory for creating WES provider instances"""
    
    @staticmethod
    def create_provider(provider_type=None):
        """
        Create a WES provider instance based on configuration.
        
        Args:
            provider_type: The type of provider to create.
                           If None, uses the configured default.
        
        Returns:
            A WesProvider instance
        """
        if provider_type is None:
            # Get from configuration
            from flask import current_app
            provider_type = current_app.config.get('WES_PROVIDER', 'aws-omics')
            
        if provider_type == 'aws-omics':
            return HealthOmicsService()
        # Add other providers as they are implemented
        else:
            raise ValueError(f"Unknown WES provider type: {provider_type}")
```

#### Update API Implementation

Update the API implementation to use the factory:

```python
# app/api/wes.py

from app.services.wes_factory import WesFactory

# Initialize WES service
wes_service = WesFactory.create_provider()

# Use wes_service instead of omics_service throughout the file
```

### 2.6 Configure Test Environment

Create a pytest configuration file:

```python
# tests/conftest.py

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
```

## 3. Running the Integration Test

To run the integration test:

1. Install test dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Set up the environment variables:
   ```bash
   export WES_API_URL=http://localhost:5000/api/ga4gh/wes/v1
   export AWS_OMICS_ROLE_ARN=your-role-arn
   ```

3. Run the test:
   ```bash
   pytest tests/integration/test_workflow_execution.py -v
   ```

## 4. Future Enhancements

1. Add support for more workflow types (CWL, Nextflow)
2. Implement additional WES providers (e.g., Cromwell, Toil)
3. Add more complex workflow examples
4. Create a mock WES provider for testing without external dependencies
5. Add performance testing for workflow execution
