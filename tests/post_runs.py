#!/usr/bin/env python
"""Create test workflow runs in the database"""
import requests

count=50
# Create test runs
states = ['QUEUED', 'INITIALIZING', 'RUNNING', 'COMPLETE', 'EXECUTOR_ERROR', 'SYSTEM_ERROR', 'CANCELED']
workflow_types = ['CWL', 'WDL']
        
for i in range(count):
    # Create a new workflow run
    payload = {
        "workflow_params": {'input': f'test_input_{i}'},
        "workflow_type": "CWL",
        "workflow_type_version": "1.0",
        'tags': {
            'name': f'test_workflow_{i}',
            'owner': 'test_user',
            'project': 'test_project'
        },
        "workflow_engine_parameters": {
           'use_spot_instances': True,
        },
        "workflow_engine": "test_engine",
        "workflow_engine_version": "1.0",
        'workflow_url': f'https://example.com/workflows/workflow_{i}.cwl',
    }
    response = requests.post('http://localhost:5000/ga4gh/wes/v1/runs', json=payload)
    if response.status_code == 200:
        print(f"Created workflow run {i} with ID: {response.json()['run_id']}")
    else:
        print(f"Failed to create workflow run {i}: {response.text}")
