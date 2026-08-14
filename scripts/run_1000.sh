#!/bin/bash
# Example script for submitting workflows to WES service

set -e

# Configuration
# The CLI takes the service root and adds /ga4gh/wes/v1 itself; the curl calls
# below still need the prefixed URL, so derive it.
export WES_API_URL="${WES_API_URL:-http://localhost:8000}"
export WES_USERNAME="${WES_USERNAME:-admin}"
export WES_PASSWORD="${WES_PASSWORD:-password}"
WES_URL="${WES_API_URL}/ga4gh/wes/v1"
USERNAME="$WES_USERNAME"
PASSWORD="$WES_PASSWORD"

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
for i in {1..1000}; do
    echo -e "\n${BLUE}[$i/1000] Submitting example workflow...${NC}"
    echo "{\"message\": \"Hello from WES $i\"}" > /tmp/wes-load-params.json
    RUN_ID=$(wes runs submit \
        --workflow-url "https://raw.githubusercontent.com/common-workflow-language/cwl-v1.2/main/examples/1st-tool.cwl" \
        --workflow-type CWL \
        --workflow-type-version v1.0 \
        --params /tmp/wes-load-params.json \
        | awk '{print $NF}')

    echo -e "${GREEN}✓ Workflow submitted: $RUN_ID${NC}\n"
done


# List all runs
echo -e "\n${BLUE}Listing all runs...${NC}"
wes runs list --limit 100

echo -e "\n${GREEN}=== Example Complete ===${NC}"