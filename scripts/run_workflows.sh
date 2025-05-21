#!/bin/bash

WES_SERVER="http://localhost/api/ga4gh/wes/v1"
ARVADOS_WORKFLOW_UUID="arvados://xngs1-abcde-123456789asdfvc"
ARVADOS_PROJECT_ID="xngs1-abcde-123456789asdfvc"

SBG_WORKFLOW_URL="sevenbridges://org/project/hello_world"
SBG_PROJECT_ID="org/project"

OMICS_WORKFLOW_URL="omics://arn:aws:omics:us-east-1:123456789:workflow/12345"

./wes_client --base-url $WES_SERVER --engine cwltool --workflow-url ../tests/workflows/hello_world.cwl
./wes_client --base-url $WES_SERVER --engine Arvados --workflow-url $ARVADOS_WORKFLOW_UUID --tags '{"project_id": "$ARVADOS_PROJECT_ID"}'
./wes_client --base-url $WES_SERVER --engine SevenBridges --workflow-url $SBG_WORKFLOW_URL --tags '{"project_id": "$SBG_PROJECT_ID"}'
./wes_client --base-url $WES_SERVER --engine AWSHealthOmics --workflow-url $OMICS_WORKFLOW_URL 
