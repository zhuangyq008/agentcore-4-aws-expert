#!/bin/bash
# ============================================================
# AWS Expert Agent — 部署脚本
#
# 使用 boto3 创建/更新 AgentCore Runtime
# （AWS CLI 暂不支持 --filesystem-configurations 参数）
# ============================================================
set -e

AWS_REGION=${AWS_REGION:-us-west-2}
AGENT_NAME="aws_expert_agent"
ECR_REPO_NAME="aws-expert-agent"
IMAGE_TAG=${IMAGE_TAG:-latest}
ROLE_NAME="AgentCoreRuntimeRole-aws-expert-agent"

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN} AWS Expert Agent — Deploy${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e " Account: ${AWS_ACCOUNT_ID}"
echo -e " Region:  ${AWS_REGION}"
echo -e " Image:   ${ECR_URI}:${IMAGE_TAG}"
echo ""

# ── 1. ECR ────────────────────────────────────────────────
echo -e "${YELLOW}[1/5] ECR${NC}"
aws ecr describe-repositories --repository-names ${ECR_REPO_NAME} --region ${AWS_REGION} >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name ${ECR_REPO_NAME} --region ${AWS_REGION} \
        --image-scanning-configuration scanOnPush=true >/dev/null
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com" 2>/dev/null
echo -e "${GREEN}  OK${NC}"

# ── 2. Build & Push ───────────────────────────────────────
echo -e "${YELLOW}[2/5] Build & Push (ARM64)${NC}"
docker build --platform linux/arm64 -t ${ECR_URI}:${IMAGE_TAG} . --quiet
docker push ${ECR_URI}:${IMAGE_TAG} --quiet
echo -e "${GREEN}  OK${NC}"

# ── 3. IAM Role ──────────────────────────────────────────
echo -e "${YELLOW}[3/5] IAM Role${NC}"
if ! aws iam get-role --role-name ${ROLE_NAME} >/dev/null 2>&1; then
    aws iam create-role --role-name ${ROLE_NAME} \
        --assume-role-policy-document '{
            "Version":"2012-10-17",
            "Statement":[{"Effect":"Allow","Principal":{"Service":"bedrock-agentcore.amazonaws.com"},"Action":"sts:AssumeRole"}]
        }' >/dev/null
    aws iam attach-role-policy --role-name ${ROLE_NAME} --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
    aws iam attach-role-policy --role-name ${ROLE_NAME} --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
    aws iam attach-role-policy --role-name ${ROLE_NAME} --policy-arn arn:aws:iam::aws:policy/CloudWatchFullAccessV2
    echo "  Waiting 10s for IAM propagation..."
    sleep 10
fi
ROLE_ARN=$(aws iam get-role --role-name ${ROLE_NAME} --query 'Role.Arn' --output text)
echo -e "${GREEN}  OK — ${ROLE_ARN}${NC}"

# ── 4. Create / Update Runtime (boto3) ───────────────────
echo -e "${YELLOW}[4/5] AgentCore Runtime (boto3)${NC}"
python3 << PYEOF
import boto3, json, sys

client = boto3.client("bedrock-agentcore-control", region_name="${AWS_REGION}")
name = "${AGENT_NAME}"
image = "${ECR_URI}:${IMAGE_TAG}"
role = "${ROLE_ARN}"

# Check if runtime exists
runtimes = client.list_agent_runtimes().get("agentRuntimes", [])
existing = next((r for r in runtimes if r["agentRuntimeName"] == name), None)

artifact = {"containerConfiguration": {"containerUri": image}}
fs_config = [{"sessionStorage": {"mountPath": "/mnt/workspace"}}]
env_vars = {"AWS_REGION": "${AWS_REGION}", "WORKSPACE": "/mnt/workspace"}

if existing:
    rid = existing["agentRuntimeId"]
    print(f"  Updating {rid}...")
    resp = client.update_agent_runtime(
        agentRuntimeId=rid,
        agentRuntimeArtifact=artifact,
        roleArn=role,
        networkConfiguration={"networkMode": "PUBLIC"},
        filesystemConfigurations=fs_config,
        environmentVariables=env_vars,
    )
    print(f"  Version: {resp.get('agentRuntimeVersion')}, Status: {resp['status']}")
else:
    print("  Creating new runtime...")
    resp = client.create_agent_runtime(
        agentRuntimeName=name,
        description="AWS Expert Agent - 庄颖勤老师 (Manufacturing)",
        agentRuntimeArtifact=artifact,
        roleArn=role,
        networkConfiguration={"networkMode": "PUBLIC"},
        filesystemConfigurations=fs_config,
        environmentVariables=env_vars,
    )
    rid = resp["agentRuntimeId"]
    print(f"  Created: {rid}, Status: {resp['status']}")

# Wait for READY
import time
for i in range(30):
    r = client.get_agent_runtime(agentRuntimeId=rid)
    if r["status"] == "READY":
        break
    print(f"  Status: {r['status']} ({(i+1)*10}s)")
    time.sleep(10)

# Get endpoint
eps = client.list_agent_runtime_endpoints(agentRuntimeId=rid)
ep = eps["runtimeEndpoints"][0]
arn = r["agentRuntimeArn"]
ep_arn = ep["agentRuntimeEndpointArn"]

# Save deployment info
info = {
    "agentName": name,
    "runtimeId": rid,
    "runtimeArn": arn,
    "endpointArn": ep_arn,
    "imageUri": image,
    "region": "${AWS_REGION}",
    "sessionStorageMountPath": "/mnt/workspace",
    "runtimeVersion": int(resp.get("agentRuntimeVersion", "1")),
}
with open("deployment-info.json", "w") as f:
    json.dump(info, f, indent=2)

print(f"  Runtime: {rid}")
print(f"  Endpoint: {ep_arn}")
print(f"  Status: {ep['status']}")
PYEOF
echo -e "${GREEN}  OK${NC}"

# ── 5. Summary ───────────────────────────────────────────
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN} Deploy Complete${NC}"
echo -e "${GREEN}========================================${NC}"
cat deployment-info.json
echo ""
echo -e "Test: ${YELLOW}python3 -c \"\$(cat <<'PY'"
echo 'import boto3,json,uuid'
echo 'c=boto3.client("bedrock-agentcore",region_name="'${AWS_REGION}'")'
echo 's=f"s-{uuid.uuid4()}"'
echo 'r=c.invoke_agent_runtime('
echo '  agentRuntimeArn="'$(python3 -c "import json;print(json.load(open('deployment-info.json'))['runtimeArn'])"  2>/dev/null)'",'
echo '  runtimeSessionId=s,'
echo '  payload=json.dumps({"input":"List skills","session_id":s}).encode(),'
echo '  contentType="application/json")'
echo 'print(json.loads(r["response"].read())["response"][:500])'
echo -e "PY\n)\"${NC}"
