#!/bin/bash
# Validate project setup

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}AWS Expert Agent - Validation${NC}"
echo -e "${GREEN}========================================${NC}"

# Check files
echo -e "\n${YELLOW}[1/5] Checking project files...${NC}"
REQUIRED_FILES=(
    "IDENTITY.md"
    "agent.py"
    "agent_runtime.py"
    "Dockerfile"
    "requirements.txt"
    "deploy.sh"
    "test.sh"
    "local_test.py"
    "README.md"
    "QUICKSTART.md"
    "PROJECT_SUMMARY.md"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file (missing)"
        exit 1
    fi
done

# Check skills
echo -e "\n${YELLOW}[2/5] Checking skills directory...${NC}"
if [ -d "skills" ]; then
    SKILL_COUNT=$(find skills -name "*.md" | wc -l)
    echo -e "${GREEN}✓${NC} skills/ directory exists ($SKILL_COUNT skills)"
    ls skills/*.md | while read skill; do
        echo "  - $(basename $skill)"
    done
else
    echo -e "${RED}✗${NC} skills/ directory not found"
    exit 1
fi

# Check Python dependencies
echo -e "\n${YELLOW}[3/5] Checking Python dependencies...${NC}"
python3 -c "
try:
    from langchain_aws import ChatBedrockConverse
    from langchain_core.tools import tool
    from langgraph.prebuilt import create_react_agent
    print('${GREEN}✓${NC} All LangChain dependencies available')
except ImportError as e:
    print('${RED}✗${NC} Missing dependency:', e)
    exit(1)
"

# Check AWS CLI
echo -e "\n${YELLOW}[4/5] Checking AWS CLI...${NC}"
if command -v aws &> /dev/null; then
    AWS_VERSION=$(aws --version)
    echo -e "${GREEN}✓${NC} AWS CLI installed: $AWS_VERSION"
    
    if aws sts get-caller-identity &> /dev/null; then
        ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
        REGION=$(aws configure get region || echo "us-east-1")
        echo -e "${GREEN}✓${NC} AWS credentials configured"
        echo "  Account: $ACCOUNT_ID"
        echo "  Region: $REGION"
    else
        echo -e "${YELLOW}⚠${NC}  AWS credentials not configured"
    fi
else
    echo -e "${RED}✗${NC} AWS CLI not installed"
fi

# Check Docker
echo -e "\n${YELLOW}[5/5] Checking Docker...${NC}"
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    echo -e "${GREEN}✓${NC} Docker installed: $DOCKER_VERSION"
    
    if docker buildx version &> /dev/null; then
        echo -e "${GREEN}✓${NC} Docker buildx available"
    else
        echo -e "${YELLOW}⚠${NC}  Docker buildx not available (needed for ARM64 builds)"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Docker not installed (needed for deployment)"
fi

# Summary
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Validation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "\n${YELLOW}Next Steps:${NC}"
echo -e "1. Local test:  ${GREEN}python3 local_test.py${NC}"
echo -e "2. Deploy:      ${GREEN}./deploy.sh${NC}"
echo -e "3. Test deploy: ${GREEN}./test.sh${NC}"

echo -e "\n${YELLOW}Documentation:${NC}"
echo -e "- Quick start:  ${GREEN}cat QUICKSTART.md${NC}"
echo -e "- Full docs:    ${GREEN}cat README.md${NC}"
echo -e "- Project info: ${GREEN}cat PROJECT_SUMMARY.md${NC}"
