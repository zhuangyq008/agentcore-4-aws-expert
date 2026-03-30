"""
AWS Expert Agent - AgentCore Runtime Version

Runs on AWS Bedrock AgentCore Runtime with:
- LangChain ReAct agent + Bedrock Claude Sonnet 4.5
- Skills & IDENTITY.md stored on AgentCore persistent filesystem (sessionStorage)
- Skills bundled in container, copied to /mnt/workspace on first invoke
- bedrock-agentcore SDK: @app.entrypoint + app.run()

Persistent filesystem reference:
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-persistent-filesystems.html
"""

import os
import json
import shutil
import subprocess
import logging
from pathlib import Path

from bedrock_agentcore.runtime import BedrockAgentCoreApp, PingStatus
from langchain_aws import ChatBedrockConverse
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = os.environ.get("AWS_REGION", "us-west-2")

# Persistent filesystem mount (sessionStorage) - available only during invocation
WORKSPACE = Path(os.environ.get("WORKSPACE", "/mnt/workspace"))

# Container-bundled source files (always available)
BUNDLED_SKILLS_DIR = Path("/app/skills")
BUNDLED_IDENTITY = Path("/app/IDENTITY.md")

# Paths on persistent filesystem
SKILLS_DIR = WORKSPACE / "skills"
IDENTITY_PATH = WORKSPACE / "IDENTITY.md"
INIT_MARKER = WORKSPACE / ".initialized"


def init_workspace() -> None:
    """
    Copy bundled skills & IDENTITY.md to the persistent filesystem
    on first invoke of a session.  Mount path is only available during
    invocation, not at container init time.
    """
    if INIT_MARKER.exists():
        return

    logger.info("Initializing workspace at %s", WORKSPACE)

    if BUNDLED_SKILLS_DIR.exists():
        if SKILLS_DIR.exists():
            shutil.rmtree(SKILLS_DIR)
        shutil.copytree(BUNDLED_SKILLS_DIR, SKILLS_DIR)
        logger.info("Skills copied to %s", SKILLS_DIR)

    if BUNDLED_IDENTITY.exists():
        shutil.copy2(BUNDLED_IDENTITY, IDENTITY_PATH)

    INIT_MARKER.write_text("initialized")
    logger.info("Workspace initialized")


def load_identity() -> str:
    """Load identity from persistent filesystem, fall back to bundled copy."""
    for path in [IDENTITY_PATH, BUNDLED_IDENTITY]:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


# ---------------------------------------------------------------------------
# Skills discovery
# ---------------------------------------------------------------------------
def _discover_skills(base: Path) -> dict[str, dict]:
    """Walk the plugins directory tree and index every .md file."""
    skills: dict[str, dict] = {}
    if not base.exists():
        return skills

    for md_file in sorted(base.rglob("*.md")):
        rel = md_file.relative_to(base)
        parts = rel.parts

        if md_file.name == "SKILL.md":
            key = parts[0]
        elif md_file.name == "README.md":
            try:
                inner_idx = next(
                    i for i, p in enumerate(parts) if p == "skills" and i > 0
                )
                sub_parts = parts[inner_idx + 2 : -1]
                key = parts[0] + "/" + "/".join(sub_parts)
            except StopIteration:
                key = str(rel.with_suffix(""))
        else:
            try:
                inner_idx = next(
                    i for i, p in enumerate(parts) if p == "skills" and i > 0
                )
                sub_parts = list(parts[inner_idx + 2 :])
                sub_parts[-1] = md_file.stem
                key = parts[0] + "/" + "/".join(sub_parts)
            except StopIteration:
                key = str(rel.with_suffix(""))

        desc = ""
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("# "):
                        desc = line[2:]
                        break
                    if line.startswith("---"):
                        continue
                    if line and not line.startswith("#"):
                        desc = line[:120]
                        break
        except Exception:
            pass

        skills[key] = {"path": md_file, "desc": desc}

    return skills


_skill_index: dict[str, dict] | None = None


def get_skill_index() -> dict[str, dict]:
    global _skill_index
    if _skill_index is None:
        _skill_index = _discover_skills(SKILLS_DIR)
        if not _skill_index:
            _skill_index = _discover_skills(BUNDLED_SKILLS_DIR)
    return _skill_index


def reset_skill_index() -> None:
    global _skill_index
    _skill_index = None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@tool
def list_skills() -> str:
    """List all available AWS skill files grouped by plugin."""
    index = get_skill_index()
    if not index:
        return "No skills found."

    groups: dict[str, list[str]] = {}
    for key, info in sorted(index.items()):
        plugin = key.split("/")[0]
        groups.setdefault(plugin, []).append(f"  - `{key}`: {info['desc']}")

    lines = ["Available skills:\n"]
    for plugin, items in sorted(groups.items()):
        lines.append(f"### {plugin}")
        lines.extend(items)
        lines.append("")
    return "\n".join(lines)


@tool
def load_skill(skill_key: str) -> str:
    """Load a specific AWS skill file by key.

    Args:
        skill_key: Skill key from list_skills, e.g. 'aws-agentic-ai',
                   'aws-cost-ops/references/cloudwatch-alarms'
    """
    index = get_skill_index()

    if skill_key in index:
        return index[skill_key]["path"].read_text(encoding="utf-8")

    matches = [k for k in index if skill_key in k]
    if len(matches) == 1:
        return index[matches[0]]["path"].read_text(encoding="utf-8")
    if matches:
        return f"Ambiguous. Did you mean:\n" + "\n".join(f"  - `{m}`" for m in matches)

    return f"Not found. Available: {', '.join(sorted(index.keys()))}"


@tool
def run_aws_cli(command: str) -> str:
    """Execute a read-only AWS CLI command.

    Args:
        command: AWS CLI command starting with 'aws '.
    """
    if not command.strip().startswith("aws "):
        return "Error: must start with 'aws '"

    blocked = ["delete", "remove", "terminate", "destroy", "put-", "create-",
               "update-", "modify-", "start-", "stop-", "reboot-"]
    for kw in blocked:
        if kw in command.lower():
            return f"Blocked: '{kw}'. Only read-only commands allowed."

    try:
        result = subprocess.run(command.split(), capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        if result.returncode != 0:
            output = f"Error: {result.stderr.strip()}"
        return (output[:4000] + "\n...(truncated)") if len(output) > 4000 else (output or "(no output)")
    except subprocess.TimeoutExpired:
        return "Timed out (30s)"
    except Exception as e:
        return f"Error: {e}"


@tool
def design_architecture(customer_name: str, requirements: str, constraints: str = "") -> str:
    """Generate a manufacturing-industry architecture design outline.

    Args:
        customer_name: Customer or project name.
        requirements: Requirements and pain points.
        constraints: Budget, timeline, team, compliance constraints.
    """
    return f"""# Architecture Design: {customer_name}
## Requirements
{requirements}
## Constraints
{constraints or 'None specified'}
## Checklist
1. Compute: Edge (Greengrass), Lambda, ECS/EKS, Batch
2. Data: Timestream, DynamoDB, S3 Data Lake
3. IoT: IoT Core, Greengrass, MQTT/OPC-UA
4. ML: SageMaker, Rekognition, Bedrock
5. Integration: EventBridge, SQS/SNS, API Gateway
6. Security: IAM, VPC, Encryption, Compliance
7. Observability: CloudWatch, X-Ray
8. Cost: Pay-per-use + Reserved estimates
Use `load_skill` for detailed guidance."""


# ---------------------------------------------------------------------------
# LangChain Agent
# ---------------------------------------------------------------------------
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        identity = load_identity()
        system_prompt = f"""{identity}

## Tools
- `list_skills` - List all skill files
- `load_skill` - Load a skill by key
- `run_aws_cli` - Execute read-only AWS CLI commands
- `design_architecture` - Generate architecture outlines

Use `list_skills` first, then `load_skill` for relevant domain knowledge."""

        llm = ChatBedrockConverse(
            model_id=MODEL_ID,
            region_name=REGION,
            temperature=0.3,
            max_tokens=4096,
        )
        _agent = create_react_agent(
            model=llm,
            tools=[list_skills, load_skill, run_aws_cli, design_architecture],
            prompt=system_prompt,
        )
    return _agent


def _extract_response(result: dict) -> str:
    for msg in reversed(result.get("messages", [])):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            if isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block["text"]
                    if isinstance(block, str):
                        return block
            else:
                return msg.content
    return ""


# ---------------------------------------------------------------------------
# AgentCore Runtime App
# ---------------------------------------------------------------------------
app = BedrockAgentCoreApp()


@app.entrypoint
def handle_request(payload):
    """
    Main entrypoint for AgentCore Runtime.
    Receives the parsed JSON payload dict directly.
    Returns a dict (serialized to JSON by the SDK).
    """
    try:
        # Initialize workspace (copy skills to persistent fs)
        init_workspace()
        reset_skill_index()

        user_input = payload.get("input", "")
        session_id = payload.get("session_id", "default-session")

        if not user_input:
            return {"error": "No input provided", "status": "error"}

        agent = get_agent()
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": session_id}},
        )

        return {
            "response": _extract_response(result),
            "session_id": session_id,
            "status": "success",
        }

    except Exception as e:
        logger.exception("Handler error")
        return {"error": str(e), "status": "error"}


@app.ping
def ping_handler():
    """Health / ping check."""
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(port=8080)
