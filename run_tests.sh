#!/bin/bash

#pip install -r requirements-dev.txt
export WES_API_URL=http://localhost:5000/api/ga4gh/wes/v1   
export AWS_OMICS_ROLE_ARN=your-role-arn
pytest tests/integration/test_workflow_execution.py -v

