#!/bin/bash
# Test AWS Expert Agent on AgentCore Runtime
#
# Uses --runtime-session-id so the persistent filesystem is enabled.
# Skills are copied to /mnt/workspace/skills on the first invoke.

set -e

AWS_REGION=${AWS_REGION:-us-east-1}
SESSION_ID="test-session-$(date +%s)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}AWS Expert Agent - Testing${NC}"
echo -e "${GREEN}========================================${NC}"

# Resolve endpoint ARN
if [ -f deployment-info.json ]; then
    ENDPOINT_ARN=$(jq -r '.endpointArn' deployment-info.json)
else
    echo -e "${YELLOW}deployment-info.json not found. Looking up runtime...${NC}"
    AGENT_NAME="aws-expert-agent"
    RUNTIME_ID=$(aws bedrock-agentcore-control list-agent-runtimes \
        --region ${AWS_REGION} \
        --query "agentRuntimeSummaries[?agentRuntimeName=='${AGENT_NAME}'].agentRuntimeId" \
        --output text)

    if [ -z "$RUNTIME_ID" ]; then
        echo "Error: Agent runtime not found. Run deploy.sh first."
        exit 1
    fi

    ENDPOINT_ARN=$(aws bedrock-agentcore-control get-agent-runtime \
        --agent-runtime-id ${RUNTIME_ID} \
        --region ${AWS_REGION} \
        --query 'agentRuntime.endpoints[?endpointName==`DEFAULT`].endpointArn' \
        --output text)
fi

echo -e "Endpoint: ${ENDPOINT_ARN}"
echo -e "Session:  ${SESSION_ID}\n"

# Helper function: invoke with runtime-session-id for persistent filesystem
invoke_agent() {
    local input="$1"
    local payload=$(python3 -c "import json; print(json.dumps({'input': '$input', 'session_id': '${SESSION_ID}'}))")

    aws bedrock-agentcore-runtime invoke-agent-runtime \
        --agent-runtime-endpoint-arn "${ENDPOINT_ARN}" \
        --runtime-session-id "${SESSION_ID}" \
        --payload "${payload}" \
        --region ${AWS_REGION} \
        --query 'payload' \
        --output text | base64 -d
}

# Test 1: List Skills (this also triggers workspace initialization)
echo -e "${YELLOW}[Test 1/3] List skills (triggers workspace init)...${NC}"
RESPONSE=$(invoke_agent "请列出所有可用的技能")
echo -e "${CYAN}Response:${NC}"
echo "${RESPONSE}" | python3 -m json.tool 2>/dev/null || echo "${RESPONSE}"
echo ""

# Test 2: Load a specific skill
echo -e "${YELLOW}[Test 2/3] Load a specific skill...${NC}"
RESPONSE=$(invoke_agent "请加载 aws-agentic-ai 的技能内容，简要概述它包含什么")
echo -e "${CYAN}Response:${NC}"
echo "${RESPONSE}" | python3 -m json.tool 2>/dev/null || echo "${RESPONSE}"
echo ""

# Test 3: Ask a manufacturing question
echo -e "${YELLOW}[Test 3/3] Manufacturing industry question...${NC}"
RESPONSE=$(invoke_agent "在制造行业中，如何使用 AWS IoT 服务实现设备的预测性维护？请简要回答。")
echo -e "${CYAN}Response:${NC}"
echo "${RESPONSE}" | python3 -m json.tool 2>/dev/null || echo "${RESPONSE}"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Testing Complete!${NC}"
echo -e "${GREEN}========================================${NC}"

# Interactive mode
echo -e "\n${YELLOW}Enter interactive mode? (y/n)${NC}"
read -r INTERACTIVE

if [ "$INTERACTIVE" == "y" ]; then
    echo -e "${CYAN}Type questions (or 'quit' to exit):${NC}\n"
    while true; do
        echo -n -e "${GREEN}[You]${NC} > "
        read -r USER_INPUT

        [ "$USER_INPUT" == "quit" ] || [ "$USER_INPUT" == "exit" ] && break
        [ -z "$USER_INPUT" ] && continue

        echo -e "${YELLOW}Thinking...${NC}"
        RESPONSE=$(invoke_agent "${USER_INPUT}")
        echo -e "${CYAN}[AWS Expert]${NC}"
        echo "${RESPONSE}" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data.get('response', data.get('error', json.dumps(data, indent=2, ensure_ascii=False))))
except:
    print(sys.stdin.read())
" 2>/dev/null || echo "${RESPONSE}"
        echo ""
    done
fi
