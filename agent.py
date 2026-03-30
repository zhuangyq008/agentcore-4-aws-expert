"""
AWS Expert Agent - LangChain + Bedrock Claude + Skills

Local interactive version. Skills are loaded from the local skills/ directory
which mirrors the plugins structure from https://github.com/zxkane/aws-skills.

For AgentCore Runtime deployment, see agent_runtime.py.
"""

import os
import json
import subprocess
from pathlib import Path

from langchain_aws import ChatBedrockConverse
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = os.environ.get("AWS_REGION", "us-east-1")
SKILLS_DIR = Path(__file__).parent / "skills"
IDENTITY_PATH = Path(__file__).parent / "IDENTITY.md"

IDENTITY_CONTENT = ""
if IDENTITY_PATH.exists():
    IDENTITY_CONTENT = IDENTITY_PATH.read_text(encoding="utf-8")

SYSTEM_PROMPT = f"""\
{IDENTITY_CONTENT}

## Available Tools

- `list_skills` - List all available AWS skill files (grouped by plugin)
- `load_skill` - Load a specific skill by key (e.g. 'aws-agentic-ai', 'aws-cost-ops/references/cloudwatch-alarms')
- `run_aws_cli` - Execute read-only AWS CLI commands
- `search_web` - Search the web for latest AWS information
- `design_architecture` - Generate architecture design outlines

Always use `list_skills` first to discover available knowledge, then `load_skill` to load
relevant content before answering domain questions.
"""


# ---------------------------------------------------------------------------
# Skills discovery
# ---------------------------------------------------------------------------
def _discover_skills(base: Path) -> dict[str, dict]:
    """
    Walk the plugins directory tree and index every .md file.

    Returns a dict keyed by a short name, e.g.:
        "aws-agentic-ai"               -> SKILL.md (main definition)
        "aws-agentic-ai/services/runtime" -> services/runtime/README.md
        "aws-cost-ops/references/cloudwatch-alarms" -> references/cloudwatch-alarms.md
    """
    skills: dict[str, dict] = {}
    if not base.exists():
        return skills

    for md_file in sorted(base.rglob("*.md")):
        rel = md_file.relative_to(base)
        parts = rel.parts

        # Build a human-friendly key
        if md_file.name == "SKILL.md":
            key = parts[0]
        elif md_file.name == "README.md":
            try:
                inner_idx = next(
                    i for i, p in enumerate(parts)
                    if p == "skills" and i > 0
                )
                sub_parts = parts[inner_idx + 2:-1]
                key = parts[0] + "/" + "/".join(sub_parts)
            except StopIteration:
                key = str(rel.with_suffix(""))
        else:
            try:
                inner_idx = next(
                    i for i, p in enumerate(parts)
                    if p == "skills" and i > 0
                )
                sub_parts = list(parts[inner_idx + 2:])
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
    return _skill_index


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@tool
def list_skills() -> str:
    """List all available AWS skill files.
    Returns skill names grouped by plugin, with descriptions.
    Use the skill key with the load_skill tool.
    """
    index = get_skill_index()
    if not index:
        return f"No skills found in {SKILLS_DIR}"

    groups: dict[str, list[str]] = {}
    for key, info in sorted(index.items()):
        plugin = key.split("/")[0]
        groups.setdefault(plugin, []).append(
            f"  - `{key}`: {info['desc']}"
        )

    lines = ["Available skills (use key with load_skill):\n"]
    for plugin, items in sorted(groups.items()):
        lines.append(f"### {plugin}")
        lines.extend(items)
        lines.append("")

    return "\n".join(lines)


@tool
def load_skill(skill_key: str) -> str:
    """Load the content of a specific AWS skill file.

    Args:
        skill_key: Key of the skill to load, as shown by list_skills.
                   Examples: 'aws-agentic-ai', 'aws-cost-ops/references/cloudwatch-alarms',
                   'serverless-eda/references/eda-patterns'
    """
    index = get_skill_index()

    if skill_key in index:
        try:
            return index[skill_key]["path"].read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading skill '{skill_key}': {e}"

    matches = [k for k in index if skill_key in k]
    if matches:
        if len(matches) == 1:
            try:
                return index[matches[0]]["path"].read_text(encoding="utf-8")
            except Exception as e:
                return f"Error reading skill '{matches[0]}': {e}"
        return (
            f"Skill '{skill_key}' not found. Did you mean one of:\n"
            + "\n".join(f"  - `{m}`" for m in matches)
        )

    available = ", ".join(sorted(index.keys()))
    return f"Skill '{skill_key}' not found.\nAvailable: {available}"


@tool
def run_aws_cli(command: str) -> str:
    """Execute an AWS CLI command and return the output.
    Only read-only commands are allowed for safety.

    Args:
        command: The AWS CLI command (e.g., 'aws s3 ls').
                 Must start with 'aws '.
    """
    if not command.strip().startswith("aws "):
        return "Error: Command must start with 'aws '."

    dangerous_keywords = [
        "delete", "remove", "terminate", "destroy",
        "put-", "create-", "update-", "modify-",
        "start-", "stop-", "reboot-",
    ]
    cmd_lower = command.lower()
    for keyword in dangerous_keywords:
        if keyword in cmd_lower:
            return (
                f"Blocked: command contains '{keyword}'. "
                "Only read-only commands allowed."
            )

    try:
        result = subprocess.run(
            command.split(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            output = f"Error (exit {result.returncode}): {result.stderr.strip()}"
        if len(output) > 4000:
            output = output[:4000] + "\n... (truncated)"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command: {e}"


@tool
def search_web(query: str) -> str:
    """Search the web for latest AWS information using tavily CLI.

    Args:
        query: Search query string about AWS topics.
    """
    try:
        result = subprocess.run(
            ["tvly", "search", query, "--max-results", "5", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return f"Search error: {result.stderr.strip()}"

        data = json.loads(result.stdout)
        results = data.get("results", [])
        if not results:
            return "No results found."

        output_lines = []
        for r in results[:5]:
            title = r.get("title", "")
            url = r.get("url", "")
            content = r.get("content", "")[:300]
            output_lines.append(f"### {title}\n{url}\n{content}\n")
        return "\n".join(output_lines)
    except subprocess.TimeoutExpired:
        return "Search timed out after 30 seconds"
    except Exception as e:
        return f"Search error: {e}"


@tool
def design_architecture(
    customer_name: str,
    requirements: str,
    constraints: str = "",
) -> str:
    """Generate an architecture design outline for manufacturing industry customers.

    Args:
        customer_name: Name of the customer or project.
        requirements: Description of customer requirements and pain points.
        constraints: Any constraints (budget, timeline, team size, compliance).
    """
    return f"""
# Architecture Design Outline: {customer_name}

## Requirements Summary
{requirements}

## Constraints
{constraints or 'No specific constraints mentioned'}

## Design Checklist for Manufacturing Industry

### 1. Compute Layer
- [ ] Edge computing (AWS IoT Greengrass)
- [ ] Real-time processing (Lambda, ECS, EKS)
- [ ] Batch processing (AWS Batch, EMR)
- [ ] Cost optimization (Spot, Graviton, Savings Plans)

### 2. Data Layer
- [ ] Time-series data (Timestream, DynamoDB)
- [ ] SCADA/MES data integration
- [ ] Data lake (S3, Lake Formation)

### 3. IoT & Edge
- [ ] Device connectivity (IoT Core, Greengrass)
- [ ] Protocol support (MQTT, OPC-UA, Modbus)
- [ ] Edge analytics

### 4. Analytics & ML
- [ ] Predictive maintenance (SageMaker)
- [ ] Quality inspection (Rekognition)
- [ ] Real-time dashboards (QuickSight, Grafana)

### 5. Integration
- [ ] Event-driven architecture (EventBridge, SNS/SQS)
- [ ] ERP/MES integration

### 6. Security
- [ ] IAM, Encryption, VPC, Compliance

### 7. Observability
- [ ] CloudWatch, X-Ray

### 8. Cost Estimate
- [ ] Pay-per-use, Reserved/Savings Plan, Total

Use `load_skill` to get detailed guidance for each area.
"""


# ---------------------------------------------------------------------------
# Agent Creation
# ---------------------------------------------------------------------------
def create_aws_expert_agent():
    """Create and return the AWS Expert Agent."""
    llm = ChatBedrockConverse(
        model_id=MODEL_ID,
        region_name=REGION,
        temperature=0.3,
        max_tokens=4096,
    )

    return create_react_agent(
        model=llm,
        tools=[list_skills, load_skill, run_aws_cli, search_web, design_architecture],
        prompt=SYSTEM_PROMPT,
    )


# ---------------------------------------------------------------------------
# Interactive Chat Loop
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("  AWS Expert Agent - 庄颖勤老师")
    print(f"  Model: {MODEL_ID}")
    print(f"  Region: {REGION}")
    print(f"  Skills: {SKILLS_DIR}")
    skill_count = len(get_skill_index())
    print(f"  Loaded: {skill_count} skill files")
    print("=" * 60)
    print("Type your question (or 'quit' to exit):\n")

    agent = create_aws_expert_agent()
    thread_id = "aws-expert-session-1"
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        try:
            user_input = input("\n[You] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        print("\n[AWS Expert] Thinking...\n")

        try:
            response = agent.invoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
            )

            messages = response.get("messages", [])
            for msg in reversed(messages):
                if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                    if isinstance(msg.content, list):
                        for block in msg.content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                print(block["text"])
                            elif isinstance(block, str):
                                print(block)
                    else:
                        print(msg.content)
                    break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
