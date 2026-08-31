#!/bin/bash
# Example script for the launcher orchestration flow: a launcher run plus the
# child runs it submits, then the progress rollup over them.
#
# Mirrors run_example.sh. Nothing here talks to AWS -- a launcher run is left
# QUEUED for its external submitter (NGS360 APIServer), so the state changes an
# AWS Batch job would report are simulated with the executor callback, which is
# also how you can exercise the endpoint by hand.
#
# Set INTERNAL_CALLBACK_API_KEY to the service's key to include those steps.

set -e

# Configuration
# The CLI takes the service root and adds /ga4gh/wes/v1 itself; the curl calls
# below still need the prefixed URL, so derive it.
export WES_API_URL="${WES_API_URL:-http://localhost:8000}"
export WES_USERNAME="${WES_USERNAME:-admin}"
export WES_PASSWORD="${WES_PASSWORD:-password}"
WES_URL="${WES_API_URL}/ga4gh/wes/v1"
PROJECT_ID="${PROJECT_ID:-P-1}"
LAUNCHER_URL="${LAUNCHER_URL:-RNASEQ-LAUNCHER:2.4.0}"
CHILD_URL="${CHILD_URL:-https://example.com/rnaseq.cwl}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== GA4GH WES Launcher Orchestration Example ===${NC}\n"

# Check if service is running
echo "Checking service availability..."
if ! curl -s -f "$WES_URL/service-info" > /dev/null; then
    echo "Error: WES service is not available at $WES_URL"
    exit 1
fi
echo -e "${GREEN}✓ Service is running${NC}\n"

# 1. The launcher run itself.
#
# --engine awsbatch is what routes this to external dispatch: the service makes
# no AWS call and leaves the run QUEUED until its submitter reports back.
echo -e "${BLUE}Submitting the launcher run...${NC}"
PARENT=$(wes runs submit \
    --workflow-url "$LAUNCHER_URL" \
    --engine awsbatch \
    --tag "ProjectId=$PROJECT_ID" \
    --tag TaskName=rnaseq-launcher \
    --param reference_model=GRCh38ERCC.ensembl91 \
    | awk '{print $NF}')
echo -e "${GREEN}✓ Launcher run: $PARENT${NC}"
echo "State: $(wes runs status "$PARENT")   (QUEUED, awaiting external dispatch)"
echo ""

# 2. The Batch job starts.
#
# In production this comes from EventBridge via the relay Lambda, or from
# APIServer reporting the jobId it got back from SubmitJob.
if [[ -n "$INTERNAL_CALLBACK_API_KEY" ]]; then
    echo -e "${BLUE}Reporting the Batch job as RUNNING...${NC}"
    curl -s -f -X POST "$WES_URL/internal/callbacks/executor-state-change" \
        -H "X-Internal-API-Key: $INTERNAL_CALLBACK_API_KEY" \
        -H 'Content-Type: application/json' \
        -d '{
              "wes_run_id": "'"$PARENT"'",
              "executor": "awsbatch",
              "executor_run_id": "batch-job-example-1",
              "status": "RUNNING",
              "event_id": "evt-example-parent-running",
              "event_time": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'",
              "log_urls": {"log_stream_name": "launcher/default/example-1"}
            }' | python3 -m json.tool
    echo -e "${GREEN}✓ State: $(wes runs status "$PARENT")${NC}\n"
else
    echo -e "${YELLOW}INTERNAL_CALLBACK_API_KEY not set -- skipping the executor"
    echo -e "callback steps. The launcher run stays QUEUED.${NC}\n"
fi

# 3. The launcher fans out. Each child carries the launcher's run id, which the
#    service promotes into the indexed parent_run_id column.
echo -e "${BLUE}Submitting two child runs...${NC}"
CHILDREN=()
for SAMPLE in sampleA sampleB; do
    CHILD=$(wes runs submit \
        --workflow-url "$CHILD_URL" \
        --engine awshealthomics \
        --tag "ProjectId=$PROJECT_ID" \
        --tag "TaskName=$SAMPLE" \
        --tag "ParentRunId=$PARENT" \
        | awk '{print $NF}')
    CHILDREN+=("$CHILD")
    echo -e "${GREEN}✓ $SAMPLE: $CHILD${NC}"
done
echo ""

# 4. Reading the lineage back.
#
# The listing is also how a restarted launcher rediscovers work it already
# submitted, so it does not resubmit it.
echo -e "${BLUE}Runs submitted by this launcher...${NC}"
wes runs list --parent "$PARENT"
echo ""

echo -e "${BLUE}Launcher progress...${NC}"
wes runs progress "$PARENT"
echo ""

echo -e "${BLUE}Launcher tree...${NC}"
wes runs tree "$PARENT"
echo ""

# 5. One child finishes, one fails -- so the rollup shows something worth
#    looking at, and the launcher's own state stays independent of both.
if [[ -n "$INTERNAL_CALLBACK_API_KEY" ]]; then
    echo -e "${BLUE}Driving the children to terminal states...${NC}"
    INDEX=0
    for FINAL in COMPLETED FAILED; do
        CHILD="${CHILDREN[$INDEX]}"
        # RUNNING first: QUEUED -> COMPLETE is not a legal transition, and the
        # service rejects the shortcut rather than papering over it.
        for STATUS in RUNNING "$FINAL"; do
            curl -s -f -X POST "$WES_URL/internal/callbacks/executor-state-change" \
                -H "X-Internal-API-Key: $INTERNAL_CALLBACK_API_KEY" \
                -H 'Content-Type: application/json' \
                -d '{
                      "wes_run_id": "'"$CHILD"'",
                      "executor": "omics",
                      "executor_run_id": "omics-example-'"$INDEX"'",
                      "status": "'"$STATUS"'",
                      "event_id": "evt-example-child-'"$INDEX"'-'"$STATUS"'",
                      "event_time": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"
                    }' > /dev/null
        done
        echo -e "${GREEN}✓ $CHILD -> $(wes runs status "$CHILD")${NC}"
        INDEX=$((INDEX + 1))
    done
    echo ""

    echo -e "${BLUE}Progress after the children finished...${NC}"
    wes runs progress "$PARENT"
    echo ""

    # The launcher's Batch job ends successfully even though a child failed:
    # parent state and child progress are deliberately separate.
    echo -e "${BLUE}Reporting the Batch job as SUCCEEDED...${NC}"
    curl -s -f -X POST "$WES_URL/internal/callbacks/executor-state-change" \
        -H "X-Internal-API-Key: $INTERNAL_CALLBACK_API_KEY" \
        -H 'Content-Type: application/json' \
        -d '{
              "wes_run_id": "'"$PARENT"'",
              "executor": "awsbatch",
              "status": "SUCCEEDED",
              "event_id": "evt-example-parent-done",
              "event_time": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"
            }' > /dev/null
    echo -e "${GREEN}✓ State: $(wes runs status "$PARENT")${NC}\n"

    # The run log carries the CloudWatch console link built from the reported
    # log stream, which is the operator's way into the launcher's own logs.
    echo -e "${BLUE}Launcher run log...${NC}"
    wes runs get "$PARENT"
    echo ""
fi

echo -e "${GREEN}=== Example Complete ===${NC}"
