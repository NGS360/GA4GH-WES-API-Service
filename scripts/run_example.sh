#!/bin/bash
# Example script for submitting workflows to WES service

set -e

# Configuration
WES_URL="${WES_URL:-http://localhost:8000/ga4gh/wes/v1}"
USERNAME="${WES_USERNAME:-admin}"
PASSWORD="${WES_PASSWORD:-password}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== GA4GH WES Example Workflow Submission ===${NC}\n"

# Check if service is running
echo "Checking service availability..."
if ! curl -s -f "$WES_URL/service-info" > /dev/null; then
    echo "Error: WES service is not available at $WES_URL"
    exit 1
fi
echo -e "${GREEN}✓ Service is running${NC}\n"

# Get service info
echo "Getting service information..."
curl -s -u "$USERNAME:$PASSWORD" "$WES_URL/service-info" | python3 -m json.tool
echo ""

# Submit example workflow
echo -e "\n${BLUE}Submitting example workflow...${NC}"
RUN_ID=$(python3 scripts/wes_client.py \
    --base-url "$WES_URL" \
    --username "$USERNAME" \
    --password "$PASSWORD" \
    submit \
    --workflow-url "https://raw.githubusercontent.com/common-workflow-language/cwl-v1.2/main/examples/1st-tool.cwl" \
    --workflow-type CWL \
    --workflow-version v1.0 \
    --workflow-params '{"message": "Hello from WES!"}' \
    | sed -n 's/.*Submitted workflow run: //p')

echo -e "${GREEN}✓ Workflow submitted: $RUN_ID${NC}\n"

# Monitor workflow status
echo "Monitoring workflow status..."
for i in {1..10}; do
    STATUS=$(python3 scripts/wes_client.py \
        --base-url "$WES_URL" \
        --username "$USERNAME" \
        --password "$PASSWORD" \
        status "$RUN_ID" \
        | python3 -c "import sys, json; print(json.load(sys.stdin)['state'])")
    
    echo "Status: $STATUS"
    
    if [[ "$STATUS" == "COMPLETE" ]] || [[ "$STATUS" == "EXECUTOR_ERROR" ]] || [[ "$STATUS" == "SYSTEM_ERROR" ]]; then
        break
    fi
    
    sleep 2
done

# Get final run log
echo -e "\n${BLUE}Getting run log...${NC}"
python3 scripts/wes_client.py \
    --base-url "$WES_URL" \
    --username "$USERNAME" \
    --password "$PASSWORD" \
    log "$RUN_ID" | python3 -m json.tool

# List all runs
echo -e "\n${BLUE}Listing all runs...${NC}"
python3 scripts/wes_client.py \
    --base-url "$WES_URL" \
    --username "$USERNAME" \
    --password "$PASSWORD" \
    list --page-size 5 | python3 -m json.tool

echo -e "\n${GREEN}=== Example Complete ===${NC}"