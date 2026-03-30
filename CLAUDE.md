# CLAUDE.md — AWS Expert Agent on Bedrock AgentCore Runtime

## Project Overview

LangChain ReAct agent (庄颖勤老师) running on AWS Bedrock AgentCore Runtime. Uses Bedrock Claude Sonnet 4.5, with 24 skill files across 5 plugins, deployed as ARM64 Graviton container to AgentCore Runtime.

## Key Files

- `agent_runtime.py` — Production AgentCore Runtime entrypoint
- `agent.py` — Local interactive CLI version
- `deploy.sh` — One-command deployment (ECR + IAM + AgentCore Runtime via boto3)
- `skills/` — 5 plugins from github.com/zxkane/aws-skills/plugins

## Pitfalls & Lessons Learned (AgentCore Runtime)

### 1. AgentCore SDK API — Use correct decorators

- `@app.entrypoint` (NOT `@app.handler()`)
- `@app.ping` (NOT `@app.health()`)
- `app.run(port=8080)` in `__main__`
- `CMD ["python", "agent_runtime.py"]` (NOT `python -m bedrock_agentcore.runtime`)

Wrong decorators cause `RuntimeClientError` and container fails to start.

### 2. @app.ping must return PingStatus enum, NOT dict

```python
# WRONG — causes AttributeError: 'dict' object has no attribute 'value'
@app.ping
def ping_handler():
    return {"status": "healthy"}

# CORRECT
from bedrock_agentcore.runtime import PingStatus

@app.ping
def ping_handler():
    return PingStatus.HEALTHY
```

The SDK calls `.value` on the return value at `_handle_ping` line 308.

### 3. sessionStorage filesystem — mount only available during invocation

- Config: `filesystemConfigurations=[{"sessionStorage": {"mountPath": "/mnt/workspace"}}]`
- The `/mnt/workspace` mount is NOT available at container init time, only during invocation
- Strategy: Bundle skills in container at `/app/skills/`, copy to `/mnt/workspace/skills/` on first invoke via `init_workspace()`
- Use `s3Configuration` is wrong; official docs use `sessionStorage`

### 4. AWS CLI does NOT support --filesystem-configurations

`aws bedrock-agentcore-control create-agent-runtime --filesystem-configurations` gives `Unknown options` error. Must use boto3:

```python
client = boto3.client("bedrock-agentcore-control", region_name="us-west-2")
client.create_agent_runtime(
    filesystemConfigurations=[{"sessionStorage": {"mountPath": "/mnt/workspace"}}],
    ...
)
```

### 5. update_agent_runtime requires roleArn and networkConfiguration

Even for updates, these are mandatory parameters. Omitting them causes validation errors:

```python
client.update_agent_runtime(
    agentRuntimeId=rid,
    agentRuntimeArtifact=artifact,
    roleArn=role,                                    # REQUIRED even on update
    networkConfiguration={"networkMode": "PUBLIC"},   # REQUIRED even on update
    filesystemConfigurations=fs_config,
    environmentVariables=env_vars,
)
```

### 6. invoke_agent_runtime — correct service and parameters

- Service client: `boto3.client("bedrock-agentcore")` (NOT `bedrock-agentcore-runtime`)
- Use `agentRuntimeArn` (NOT endpoint ARN)
- `runtimeSessionId` minimum length: 33 characters. Use `f"session-{uuid.uuid4()}"` (44 chars)
- Response key: `response["response"]` (NOT `response["payload"]`)

```python
from botocore.config import Config

# Increase timeout for complex agent invocations (default 60s is too short)
config = Config(read_timeout=300)
client = boto3.client("bedrock-agentcore", region_name="us-west-2", config=config)

response = client.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:...:runtime/...",
    runtimeSessionId=f"session-{uuid.uuid4()}",
    payload=json.dumps({"input": "...", "session_id": "..."}).encode(),
    contentType="application/json"
)
result = json.loads(response["response"].read().decode("utf-8"))
```

### 7. boto3 read_timeout for agent invocations

Default boto3 read timeout is 60 seconds. Complex agent invocations (multi-tool ReAct chains) easily exceed this. Always set `Config(read_timeout=300)`.

### 8. AWS CLI Chinese encoding issue

`invoke_agent_runtime` with Chinese characters in payload via AWS CLI causes `string argument should contain only ASCII characters`. Use boto3 for all invocations.

### 9. IAM Role — don't forget CloudWatch permissions

The runtime needs CloudWatch for logging and metrics. Attach these policies:

- `arn:aws:iam::aws:policy/ReadOnlyAccess` — run_aws_cli read-only commands
- `arn:aws:iam::aws:policy/AmazonBedrockFullAccess` — invoke Claude model
- `arn:aws:iam::aws:policy/CloudWatchFullAccessV2` — runtime logging and monitoring

## Build & Deploy

```bash
# One-command deploy (builds, pushes, creates/updates runtime)
AWS_REGION=us-west-2 bash deploy.sh

# Local test
python3 local_test.py
python3 local_test.py -i  # interactive mode
```

## Model

`global.anthropic.claude-sonnet-4-5-20250929-v1:0` — cross-region inference endpoint
