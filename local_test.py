#!/usr/bin/env python3
"""
Local testing script for AWS Expert Agent.
Tests core functionality without requiring AgentCore Runtime deployment.
"""

import os
import sys
from pathlib import Path

os.environ["AWS_REGION"] = os.environ.get("AWS_REGION", "us-east-1")
sys.path.insert(0, str(Path(__file__).parent))

from agent import (
    create_aws_expert_agent,
    get_skill_index,
    list_skills,
    load_skill,
    MODEL_ID,
    REGION,
    SKILLS_DIR,
)


def print_agent_response(response):
    for msg in reversed(response.get("messages", [])):
        if hasattr(msg, "type") and msg.type == "ai" and msg.content:
            if isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        print(f"Response:\n{block['text']}\n")
                        return
                    elif isinstance(block, str):
                        print(f"Response:\n{block}\n")
                        return
            else:
                print(f"Response:\n{msg.content}\n")
                return


def test_basic_functionality():
    print("=" * 60)
    print("  AWS Expert Agent - Local Test")
    print("=" * 60)
    print(f"Model:  {MODEL_ID}")
    print(f"Region: {REGION}")
    print(f"Skills: {SKILLS_DIR}")

    # Check skills
    index = get_skill_index()
    print(f"Indexed: {len(index)} skill files")
    print("=" * 60)

    if not index:
        print("\nNo skills found. Ensure skills/ has been populated from:")
        print("  https://github.com/zxkane/aws-skills/tree/main/plugins")
        return False

    # Test 1: list_skills tool
    print("\n[Test 1] list_skills tool")
    print("-" * 40)
    result = list_skills.invoke({})
    print(result[:500])
    if "Available skills" not in result:
        print("FAIL: unexpected output")
        return False
    print("PASS\n")

    # Test 2: load_skill tool (main skill definition)
    print("[Test 2] load_skill tool (aws-agentic-ai)")
    print("-" * 40)
    result = load_skill.invoke({"skill_key": "aws-agentic-ai"})
    if "not found" in result.lower():
        print(f"FAIL: {result}")
        return False
    print(f"Loaded {len(result)} chars")
    print("PASS\n")

    # Test 3: load_skill with nested path
    print("[Test 3] load_skill tool (nested reference)")
    print("-" * 40)
    # Try to load a reference doc
    nested_keys = [k for k in index if "references" in k or "services" in k]
    if nested_keys:
        test_key = nested_keys[0]
        result = load_skill.invoke({"skill_key": test_key})
        if "not found" in result.lower():
            print(f"FAIL: {result}")
            return False
        print(f"Loaded '{test_key}': {len(result)} chars")
    else:
        print("SKIP: no nested skills found")
    print("PASS\n")

    # Test 4: Create agent and ask a question
    print("[Test 4] Agent question (Bedrock Claude)")
    print("-" * 40)
    agent = create_aws_expert_agent()
    response = agent.invoke(
        {"messages": [{"role": "user", "content": "请简要介绍 AWS Lambda"}]},
        config={"configurable": {"thread_id": "test"}},
    )
    print_agent_response(response)
    print("PASS\n")

    print("=" * 60)
    print("  All Tests Passed!")
    print("=" * 60)
    return True


def interactive_mode():
    print("\n" + "=" * 60)
    print("  Interactive Mode - 庄颖勤老师")
    print("=" * 60)
    print("Type questions (or 'quit' to exit):\n")

    agent = create_aws_expert_agent()
    thread_id = "interactive-session"

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
                config={"configurable": {"thread_id": thread_id}},
            )
            print_agent_response(response)
        except Exception as e:
            print(f"Error: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test AWS Expert Agent locally")
    parser.add_argument("-i", "--interactive", action="store_true",
                        help="Run in interactive mode after tests")
    parser.add_argument("--skip-tests", action="store_true",
                        help="Skip automated tests, go directly to interactive mode")
    args = parser.parse_args()

    if not args.skip_tests:
        success = test_basic_functionality()
        if not success:
            sys.exit(1)

    if args.interactive or args.skip_tests:
        interactive_mode()


if __name__ == "__main__":
    main()
