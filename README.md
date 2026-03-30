# AWS Expert Agent — 庄颖勤老师

基于 LangChain + AWS Bedrock Claude Sonnet 4.5 构建的 AWS 解决方案架构专家 Agent，专注制造行业，运行于 AWS Bedrock AgentCore Runtime。

---

## 1. 概述

| 项目 | 说明 |
|------|------|
| **Agent 名称** | 庄颖勤老师 |
| **角色定位** | AWS 解决方案架构专家（制造行业） |
| **LLM** | Bedrock Claude Sonnet 4.5 (`global.anthropic.claude-sonnet-4-5-20250929-v1:0`) |
| **框架** | LangChain + LangGraph ReAct Agent |
| **运行环境** | AWS Bedrock AgentCore Runtime（Serverless Container, ARM64 Graviton） |
| **Skills 来源** | [github.com/zxkane/aws-skills/plugins](https://github.com/zxkane/aws-skills/tree/main/plugins) |
| **持久化存储** | AgentCore sessionStorage（`/mnt/workspace`） |

### 核心能力

- 架构设计 / 服务选型 / PoC 提案 / Well-Architected 审查
- 成本优化 / 迁移规划（6R） / 竞品比较（Azure / GCP）
- 制造行业专长：智能工厂、IoT、预测性维护、供应链优化、质量管理

### 可用工具

| 工具 | 功能 |
|------|------|
| `list_skills` | 列出全部 24 个 skill 文件（5 个 plugin 分组） |
| `load_skill` | 按 key 加载指定 skill 内容，支持模糊匹配 |
| `run_aws_cli` | 执行只读 AWS CLI 命令（已内置安全过滤） |
| `design_architecture` | 生成制造业架构设计大纲（结构化 checklist） |

---

## 2. 项目结构

```
aws-expert-agent/
├── README.md               ← 本文档
├── IDENTITY.md             ← Agent 身份定义
│
├── agent_runtime.py        ← AgentCore Runtime 版本（生产）
├── agent.py                ← 本地交互式 CLI 版本（开发）
├── local_test.py           ← 本地自动化测试
│
├── Dockerfile              ← ARM64 容器（Python 3.11 + AWS CLI v2）
├── requirements.txt        ← Python 依赖
│
├── deploy.sh               ← 部署脚本（boto3，含 sessionStorage）
├── test.sh                 ← 远程测试脚本
├── validate.sh             ← 环境验证脚本
│
├── deployment-info.json    ← 部署信息（自动生成）
├── .gitignore
│
└── skills/                 ← Skills 知识库（来自 aws-skills repo）
    ├── aws-agentic-ai/     ← AgentCore 7 大服务
    ├── aws-cdk/            ← CDK 开发模式
    ├── aws-common/         ← MCP 服务器配置
    ├── aws-cost-ops/       ← 成本优化 + CloudWatch 告警
    └── serverless-eda/     ← 无服务器 + EDA 模式
```

---

## 3. 当前部署信息

| 项目 | 值 |
|------|-----|
| **Runtime ID** | `aws_expert_agent-8bkRCF6kch` |
| **Runtime ARN** | `arn:aws:bedrock-agentcore:us-west-2:284367710968:runtime/aws_expert_agent-8bkRCF6kch` |
| **Endpoint ARN** | `arn:aws:bedrock-agentcore:us-west-2:284367710968:runtime/aws_expert_agent-8bkRCF6kch/runtime-endpoint/DEFAULT` |
| **Region** | `us-west-2` |
| **AWS Account** | `284367710968` |
| **ECR Image** | `284367710968.dkr.ecr.us-west-2.amazonaws.com/aws-expert-agent:latest` |
| **Version** | 2 |
| **Status** | READY |

---

## 4. 快速开始

### 4.1 本地测试（无需部署）

```bash
cd aws-expert-agent

# 验证环境
./validate.sh

# 自动化测试（3 个用例）
python3 local_test.py

# 交互式对话
python3 local_test.py -i

# 或直接 CLI
python3 agent.py
```

### 4.2 调用已部署的 Agent

```python
import boto3, json, uuid

client = boto3.client("bedrock-agentcore", region_name="us-west-2")
session_id = f"my-session-{uuid.uuid4()}"

response = client.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:us-west-2:284367710968:runtime/aws_expert_agent-8bkRCF6kch",
    runtimeSessionId=session_id,
    payload=json.dumps({
        "input": "在制造行业中，如何使用 AWS IoT 实现预测性维护？",
        "session_id": session_id
    }).encode("utf-8"),
    contentType="application/json"
)

result = json.loads(response["response"].read().decode("utf-8"))
print(result["response"])
```

> **注意**：`runtimeSessionId` 最少 33 字符，建议使用 UUID 格式。使用相同 `runtimeSessionId` 可复用会话（持久化文件系统在 session 间保留）。

---

## 5. 部署指南

### 5.1 前置条件

| 条件 | 检查命令 |
|------|----------|
| AWS CLI v2 | `aws --version` |
| Docker + buildx | `docker buildx version` |
| Python 3.11+ | `python3 --version` |
| IAM 权限 | `bedrock-agentcore:*`, `ecr:*`, `iam:CreateRole` |

```bash
# 一键验证
./validate.sh
```

### 5.2 全新部署

```bash
export AWS_REGION=us-west-2

# Step 1: 创建 ECR 仓库
aws ecr create-repository --repository-name aws-expert-agent --region $AWS_REGION

# Step 2: 登录 ECR
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin \
  $(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com

# Step 3: 构建 & 推送镜像（ARM64）
ECR_URI="$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$AWS_REGION.amazonaws.com/aws-expert-agent"
docker build --platform linux/arm64 -t $ECR_URI:latest .
docker push $ECR_URI:latest

# Step 4: 创建 IAM 角色
# 见下方 "IAM 角色配置"

# Step 5: 通过 boto3 创建 Runtime（CLI 暂不支持 filesystemConfigurations）
python3 deploy.sh   # 或手动执行下方 Python 代码
```

### 5.3 通过 boto3 创建 Runtime

> **重要**：AWS CLI `create-agent-runtime` 暂不支持 `--filesystem-configurations` 参数，必须使用 boto3。

```python
import boto3

client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")

response = client.create_agent_runtime(
    agentRuntimeName="aws_expert_agent",
    description="AWS Expert Agent - 庄颖勤老师 (Manufacturing)",
    agentRuntimeArtifact={
        "containerConfiguration": {
            "containerUri": "<ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/aws-expert-agent:latest"
        }
    },
    roleArn="arn:aws:iam::<ACCOUNT_ID>:role/AgentCoreRuntimeRole-aws-expert-agent",
    networkConfiguration={"networkMode": "PUBLIC"},
    filesystemConfigurations=[
        {"sessionStorage": {"mountPath": "/mnt/workspace"}}
    ],
    environmentVariables={
        "AWS_REGION": "us-west-2",
        "WORKSPACE": "/mnt/workspace"
    }
)

print(f"Runtime ID: {response['agentRuntimeId']}")
print(f"Status: {response['status']}")
```

### 5.4 更新已有 Runtime

```python
client.update_agent_runtime(
    agentRuntimeId="<RUNTIME_ID>",
    agentRuntimeArtifact={
        "containerConfiguration": {
            "containerUri": "<ACCOUNT_ID>.dkr.ecr.us-west-2.amazonaws.com/aws-expert-agent:v2"
        }
    },
    roleArn="arn:aws:iam::<ACCOUNT_ID>:role/AgentCoreRuntimeRole-aws-expert-agent",
    networkConfiguration={"networkMode": "PUBLIC"},
    filesystemConfigurations=[
        {"sessionStorage": {"mountPath": "/mnt/workspace"}}
    ]
)
```

### 5.5 IAM 角色配置

**信任策略**：

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
```

**附加策略**：

| 策略 | 用途 |
|------|------|
| `arn:aws:iam::aws:policy/ReadOnlyAccess` | `run_aws_cli` 工具执行只读命令 |
| `arn:aws:iam::aws:policy/AmazonBedrockFullAccess` | 容器内调用 Claude 模型 |

---

## 6. 架构设计

### 6.1 整体架构

```
                              ┌─────────────────────────────────────┐
                              │     AgentCore Runtime (MicroVM)     │
                              │                                     │
                              │  ┌───────────────────────────────┐  │
 invoke_agent_runtime ───────▶│  │  Container (ARM64)            │  │
 (boto3 / AWS CLI)            │  │  ┌─────────────────────────┐  │  │
                              │  │  │  agent_runtime.py        │  │  │
                              │  │  │  ┌─────────┐            │  │  │──── Bedrock Claude
                              │  │  │  │ LangChain│ ReAct Agent│  │  │     Sonnet 4.5
                              │  │  │  │ + Tools  │            │  │  │
                              │  │  │  └─────────┘            │  │  │
                              │  │  │  IDENTITY.md (bundled)   │  │  │
                              │  │  └─────────────────────────┘  │  │
                              │  └───────────────────────────────┘  │
                              │                                     │
                              │  ┌───────────────────────────────┐  │
                              │  │  /mnt/workspace (sessionStorage)│  │
                              │  │  ├── skills/ (24 files)       │  │
                              │  │  ├── IDENTITY.md              │  │
                              │  │  └── .initialized             │  │
                              │  └───────────────────────────────┘  │
                              └─────────────────────────────────────┘
```

### 6.2 持久化文件系统（sessionStorage）

参考文档：[runtime-persistent-filesystems.html](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-persistent-filesystems.html)

**工作流程**：

1. **首次 invoke**：MicroVM 启动，`/mnt/workspace` 为空目录
2. **`init_workspace()`**：将容器内 `/app/skills/` 和 `/app/IDENTITY.md` 复制到 `/mnt/workspace/`，写 `.initialized` 标记
3. **后续 invoke（同 session）**：检测到 `.initialized`，跳过复制
4. **Session 停止**：数据异步持久化到 durable storage
5. **Session 恢复（同 `runtimeSessionId`）**：新 MicroVM 启动，`/mnt/workspace` 自动恢复

**关键限制**：

| 项目 | 值 |
|------|-----|
| 最大容量 | 1 GB / session |
| 数据保留 | 14 天无访问后自动清除 |
| 协议 | NFS v4（localhost） |
| 不支持 | hard link, device file, FIFO, UNIX socket, xattr, fallocate |

> **注意**：mount path 仅在 invocation 期间可用，不能在容器初始化阶段访问。这就是为什么 `init_workspace()` 在 `@app.entrypoint` 中调用而不是在模块级别。

### 6.3 Skills 知识库

来源：`https://github.com/zxkane/aws-skills/tree/main/plugins`（5 个 plugin，27 个文件）

| Plugin | Skill 数 | 涵盖内容 |
|--------|----------|---------|
| **aws-agentic-ai** | 11 md + 2 sh | AgentCore 7 大服务（Gateway, Runtime, Memory, Identity, Code Interpreter, Browser, Observability） |
| **aws-cdk** | 2 md + 1 sh | CDK 开发模式、Construct 最佳实践 |
| **aws-common** | 1 md | MCP 服务器配置 |
| **aws-cost-ops** | 3 md | 成本优化、CloudWatch 告警、运维模式 |
| **serverless-eda** | 7 md | 无服务器架构、EDA 模式、部署 / 安全 / 可观测性 / 性能最佳实践 |

**更新 Skills**：

```bash
# 拉取最新 skills
git clone --depth 1 https://github.com/zxkane/aws-skills.git /tmp/aws-skills
rm -rf skills && mkdir skills
cp -r /tmp/aws-skills/plugins/* skills/

# 重新构建 & 推送镜像，然后 update_agent_runtime
```

---

## 7. API 参考

### 7.1 请求格式

```json
{
  "input": "用户问题（支持中英文）",
  "session_id": "可选，用于 LangGraph 内部 thread_id"
}
```

### 7.2 响应格式

```json
{
  "response": "Agent 的回答文本",
  "session_id": "回传的 session_id",
  "status": "success"
}
```

错误响应：

```json
{
  "error": "错误描述",
  "status": "error"
}
```

### 7.3 调用示例

#### Python（推荐）

```python
import boto3, json, uuid

client = boto3.client("bedrock-agentcore", region_name="us-west-2")
session_id = f"session-{uuid.uuid4()}"

response = client.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:us-west-2:284367710968:runtime/aws_expert_agent-8bkRCF6kch",
    runtimeSessionId=session_id,
    payload=json.dumps({"input": "你的问题", "session_id": session_id}).encode("utf-8"),
    contentType="application/json"
)

result = json.loads(response["response"].read().decode("utf-8"))
print(result["response"])
```

#### AWS CLI

```bash
# 注意：正确命令是 bedrock-agentcore（非 bedrock-agentcore-runtime）
# 中文 payload 可能导致编码错误，建议用英文或 boto3
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "arn:aws:bedrock-agentcore:us-west-2:284367710968:runtime/aws_expert_agent-8bkRCF6kch" \
  --runtime-session-id "my-session-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" \
  --payload '{"input": "List all available skills", "session_id": "my-session"}' \
  --region us-west-2 \
  /tmp/response.bin

cat /tmp/response.bin
```

### 7.4 管理操作

```bash
# 查看 Runtime 状态
aws bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id aws_expert_agent-8bkRCF6kch --region us-west-2

# 列出所有 Runtime
aws bedrock-agentcore-control list-agent-runtimes --region us-west-2

# 列出 Endpoints
python3 -c "
import boto3, json
c = boto3.client('bedrock-agentcore-control', region_name='us-west-2')
r = c.list_agent_runtime_endpoints(agentRuntimeId='aws_expert_agent-8bkRCF6kch')
print(json.dumps(r['runtimeEndpoints'], indent=2, default=str))
"
```

---

## 8. 运维手册

### 8.1 更新 Agent 代码

```bash
# 1. 修改 agent_runtime.py
# 2. 重新构建并推送镜像
docker build --platform linux/arm64 -t $ECR_URI:v2 .
docker push $ECR_URI:v2

# 3. 更新 Runtime（boto3）
python3 -c "
import boto3
c = boto3.client('bedrock-agentcore-control', region_name='us-west-2')
c.update_agent_runtime(
    agentRuntimeId='aws_expert_agent-8bkRCF6kch',
    agentRuntimeArtifact={'containerConfiguration': {'containerUri': '$ECR_URI:v2'}},
    roleArn='arn:aws:iam::284367710968:role/AgentCoreRuntimeRole-aws-expert-agent',
    networkConfiguration={'networkMode': 'PUBLIC'},
    filesystemConfigurations=[{'sessionStorage': {'mountPath': '/mnt/workspace'}}]
)
"
```

> **注意**：更新 Runtime 版本会清除所有 session 的持久化文件系统。下次 invoke 时 `init_workspace()` 会重新初始化。

### 8.2 监控

```bash
# CloudWatch Logs（日志组名因 Runtime 而异，查询最新的）
aws logs describe-log-groups --region us-west-2 \
  --query 'logGroups[?contains(logGroupName, `aws_expert_agent`)].logGroupName'

# Bedrock 调用日志
aws logs tail /aws/bedrock/invocation-logs --follow --region us-west-2
```

### 8.3 故障排查

| 问题 | 排查 |
|------|------|
| `RuntimeClientError: An error occurred when starting the runtime` | 容器启动失败。检查 Dockerfile CMD、端口 8080、AgentCore SDK API（`@app.entrypoint` + `app.run()`） |
| `runtimeSessionId min length: 33` | Session ID 至少 33 字符，用 UUID 格式 |
| CLI `Unknown options: --filesystem-configurations` | CLI 暂不支持此参数，改用 boto3 |
| CLI payload 中文 `string argument should contain only ASCII characters` | 改用 boto3，或用英文 payload |
| Skills 未加载 | 检查容器内 `/app/skills/` 是否正确打包（`docker run --rm <image> ls /app/skills/`）|

### 8.4 清理资源

```bash
ACCOUNT_ID=284367710968
REGION=us-west-2

# 删除 Runtime
python3 -c "
import boto3
c = boto3.client('bedrock-agentcore-control', region_name='$REGION')
c.delete_agent_runtime(agentRuntimeId='aws_expert_agent-8bkRCF6kch')
"

# 删除 ECR 仓库
aws ecr delete-repository --repository-name aws-expert-agent --force --region $REGION

# 删除 IAM 角色
aws iam detach-role-policy --role-name AgentCoreRuntimeRole-aws-expert-agent \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
aws iam detach-role-policy --role-name AgentCoreRuntimeRole-aws-expert-agent \
  --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
aws iam delete-role --role-name AgentCoreRuntimeRole-aws-expert-agent
```

---

## 9. 成本参考

| 服务 | 计费方式 | 月估算（中等使用） |
|------|----------|-------------------|
| AgentCore Runtime | vCPU·秒 + GB·秒 | 按实际 invoke 时长计费 |
| Bedrock Claude Sonnet 4.5 | $3/M input tokens, $15/M output tokens | ~$50–200 |
| ECR | $0.10/GB·月 | < $1 |
| CloudWatch Logs | $0.50/GB | < $1 |

> 建议：定期监控 Bedrock token 用量，必要时优化 system prompt 和 skill 加载策略。

---

## 10. 踩坑记录

以下问题在开发部署过程中已解决，记录以供参考：

| # | 问题 | 原因 | 解决方案 |
|---|------|------|----------|
| 1 | AWS CLI 无 `--filesystem-configurations` 参数 | CLI 版本尚未支持此 API 字段 | 改用 boto3 `create_agent_runtime()` / `update_agent_runtime()` |
| 2 | AgentCore SDK 无 `@app.handler()` / `@app.health()` | SDK API 与文档示例不一致 | 正确用法：`@app.entrypoint`、`@app.ping`、`app.run(port=8080)` |
| 3 | 容器启动命令错误 | `python -m bedrock_agentcore.runtime` 不是正确入口 | `CMD ["python", "agent_runtime.py"]`，在 `__main__` 中调用 `app.run()` |
| 4 | Session ID 验证失败 | `runtimeSessionId` 最少 33 字符 | 使用 `f"session-{uuid.uuid4()}"` 格式（52 字符） |
| 5 | CLI 中文 payload 编码错误 | AWS CLI 不支持非 ASCII payload | 改用 boto3 |
| 6 | `update_agent_runtime` 缺少必需参数 | `roleArn` 和 `networkConfiguration` 是必需参数 | 更新时也需要传入所有必需参数 |
| 7 | mount path 在容器初始化时不可用 | sessionStorage 仅在 invocation 期间挂载 | `init_workspace()` 在 `@app.entrypoint` 中调用，非模块级别 |

---

## 附录 A：完整 Skills 索引

```
aws-agentic-ai                                    → SKILL.md（AgentCore 主文档）
aws-agentic-ai/cross-service/credential-management → 跨服务凭证管理
aws-agentic-ai/services/browser                    → 浏览器服务
aws-agentic-ai/services/code-interpreter           → 代码解释器服务
aws-agentic-ai/services/gateway                    → 网关服务
aws-agentic-ai/services/gateway/deployment-strategies → 网关部署策略
aws-agentic-ai/services/gateway/troubleshooting-guide → 网关故障排查
aws-agentic-ai/services/identity                   → 身份服务
aws-agentic-ai/services/memory                     → 记忆服务
aws-agentic-ai/services/observability              → 可观测性服务
aws-agentic-ai/services/runtime                    → 运行时服务
aws-cdk                                            → CDK 开发主文档
aws-cdk/references/cdk-patterns                    → CDK 模式和最佳实践
aws-common                                         → MCP 服务器配置
aws-cost-ops                                       → 成本运营主文档
aws-cost-ops/references/cloudwatch-alarms          → CloudWatch 告警配置参考
aws-cost-ops/references/operations-patterns        → 成本与运维模式
serverless-eda                                     → 无服务器 EDA 主文档
serverless-eda/references/deployment-best-practices → 部署最佳实践
serverless-eda/references/eda-patterns             → 事件驱动架构模式
serverless-eda/references/observability-best-practices → 可观测性最佳实践
serverless-eda/references/performance-optimization → 性能优化
serverless-eda/references/security-best-practices  → 安全最佳实践
serverless-eda/references/serverless-patterns      → 无服务器架构模式
```

---

## 附录 B：依赖版本

```
bedrock-agentcore >= 0.1.0     # AgentCore Runtime SDK
langchain         >= 0.3.0     # LangChain 框架
langchain-aws     >= 0.2.0     # Bedrock 集成
langchain-core    >= 0.3.0     # 核心抽象
langgraph         >= 0.2.0     # ReAct Agent
boto3             >= 1.35.0    # AWS SDK
```

---

## 附录 C：参考资料

- [AgentCore Runtime 文档](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [AgentCore 持久化文件系统](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-persistent-filesystems.html)
- [AgentCore API Reference](https://docs.aws.amazon.com/bedrock-agentcore-control/latest/APIReference/)
- [LangChain 文档](https://python.langchain.com/)
- [aws-skills 仓库](https://github.com/zxkane/aws-skills)
