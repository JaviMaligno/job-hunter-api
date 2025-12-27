#!/usr/bin/env python3
"""
Claude Code CLI Fallback Script for manual intervention.

This script is invoked when automated job application encounters blockers
that cannot be resolved automatically (complex CAPTCHAs, login, etc.).

It prepares context for Claude Code CLI to assist with manual resolution.

Usage:
    # Resolve an intervention
    poetry run python scripts/claude_code_fallback.py --intervention <id>

    # Resume a paused session
    poetry run python scripts/claude_code_fallback.py --session <id>

    # Direct URL with context
    poetry run python scripts/claude_code_fallback.py --url <url> --task "Complete job application"
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


async def get_intervention_context(intervention_id: str) -> dict | None:
    """Fetch intervention details from API."""
    import httpx

    api_url = os.getenv("API_URL", "http://localhost:8000")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{api_url}/api/applications/v2/interventions/{intervention_id}"
            )
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching intervention: {response.status_code}")
                return None
        except Exception as e:
            print(f"Failed to fetch intervention: {e}")
            return None


async def get_session_context(session_id: str) -> dict | None:
    """Fetch session details from API."""
    import httpx

    api_url = os.getenv("API_URL", "http://localhost:8000")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{api_url}/api/applications/v2/sessions/{session_id}"
            )
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error fetching session: {response.status_code}")
                return None
        except Exception as e:
            print(f"Failed to fetch session: {e}")
            return None


def generate_claude_prompt(context: dict, task_type: str) -> str:
    """Generate a prompt for Claude Code CLI."""

    if task_type == "intervention":
        prompt = f"""# Job Application Intervention Required

## Context
- **Type**: {context.get('intervention_type', 'unknown')}
- **Title**: {context.get('title', 'Manual Intervention Needed')}
- **Description**: {context.get('description', '')}
- **Current URL**: {context.get('current_url', 'N/A')}
- **CAPTCHA Type**: {context.get('captcha_type', 'N/A')}

## Instructions
{context.get('instructions', 'Please resolve this blocker manually.')}

## Task
Use the Chrome DevTools MCP to:
1. Navigate to the current URL if needed
2. Analyze the page to understand the blocker
3. Complete any required manual actions (solve CAPTCHA, login, etc.)
4. Continue filling the application form if possible
5. Report back what was accomplished

## Available MCP Tools
- `take_snapshot` - Get current page state
- `click` - Click elements by UID
- `fill` - Fill form fields
- `navigate_page` - Navigate to URL
- `take_screenshot` - Capture page state

Start by taking a snapshot to see the current page state.
"""

    elif task_type == "session":
        prompt = f"""# Resume Job Application Session

## Context
- **Job URL**: {context.get('job_url', 'N/A')}
- **Status**: {context.get('status', 'unknown')}
- **Current Step**: {context.get('current_step', 1)}
- **Fields Filled**: {len(context.get('fields_filled', {}))}
- **Blocker**: {context.get('blocker_type', 'None')}

## Progress So Far
Steps completed: {context.get('steps_completed', [])}

## Task
Use the Chrome DevTools MCP to:
1. Navigate to the job URL
2. Review current form state
3. Continue filling from where we left off
4. Handle any blockers encountered
5. Submit or pause as appropriate

Start by navigating to the URL and taking a snapshot.
"""

    else:  # direct URL
        prompt = f"""# Manual Job Application Task

## URL
{context.get('url', 'No URL provided')}

## Task
{context.get('task', 'Complete the job application')}

## Instructions
Use the Chrome DevTools MCP to:
1. Navigate to the URL
2. Analyze the page structure
3. Fill in application forms with user data
4. Handle any CAPTCHAs or blockers
5. Submit when ready

Start by navigating and taking a snapshot.
"""

    return prompt


def create_claude_context_file(prompt: str, output_path: Path) -> Path:
    """Write context to a file for Claude Code to read."""
    context_file = output_path / "intervention_context.md"
    context_file.write_text(prompt, encoding="utf-8")
    return context_file


def launch_claude_code(context_file: Path, url: str | None = None):
    """Launch Claude Code CLI with the context."""

    # Check if claude command is available
    try:
        result = subprocess.run(
            ["where", "claude"] if sys.platform == "win32" else ["which", "claude"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("Claude Code CLI not found. Please install it first:")
            print("  npm install -g @anthropic-ai/claude-code")
            print("\nManual context saved to:", context_file)
            return False
    except FileNotFoundError:
        print("Claude Code CLI not found.")
        print("\nManual context saved to:", context_file)
        return False

    # Prepare command
    cmd = ["claude"]

    # Add initial prompt
    initial_prompt = f"Please read the context file at {context_file} and help me complete this task."
    if url:
        initial_prompt += f" The target URL is {url}"

    print("\n" + "=" * 60)
    print("LAUNCHING CLAUDE CODE CLI")
    print("=" * 60)
    print(f"\nContext file: {context_file}")
    if url:
        print(f"Target URL: {url}")
    print("\nStarting Claude Code...")
    print("=" * 60 + "\n")

    # Launch Claude Code
    try:
        # On Windows, use start to open in new terminal
        if sys.platform == "win32":
            subprocess.run(
                ["cmd", "/c", "start", "cmd", "/k", "claude", "--print", initial_prompt],
                cwd=context_file.parent
            )
        else:
            subprocess.run(
                ["claude", "--print", initial_prompt],
                cwd=context_file.parent
            )
        return True
    except Exception as e:
        print(f"Failed to launch Claude Code: {e}")
        return False


async def resolve_intervention(intervention_id: str):
    """Mark intervention as resolved after manual handling."""
    import httpx

    api_url = os.getenv("API_URL", "http://localhost:8000")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{api_url}/api/applications/v2/interventions/{intervention_id}/resolve",
                json={"action": "continue", "notes": "Resolved via Claude Code CLI"}
            )
            if response.status_code == 200:
                print(f"Intervention {intervention_id} marked as resolved")
                return True
            else:
                print(f"Failed to resolve intervention: {response.status_code}")
                return False
        except Exception as e:
            print(f"Failed to resolve intervention: {e}")
            return False


async def main():
    parser = argparse.ArgumentParser(
        description="Claude Code CLI Fallback for job application interventions"
    )

    parser.add_argument(
        "--intervention", "-i",
        help="Intervention ID to resolve"
    )
    parser.add_argument(
        "--session", "-s",
        help="Session ID to resume"
    )
    parser.add_argument(
        "--url", "-u",
        help="Direct URL for manual application"
    )
    parser.add_argument(
        "--task", "-t",
        default="Complete the job application",
        help="Task description for direct URL mode"
    )
    parser.add_argument(
        "--output", "-o",
        default=".",
        help="Output directory for context file"
    )
    parser.add_argument(
        "--no-launch",
        action="store_true",
        help="Don't launch Claude Code, just generate context file"
    )
    parser.add_argument(
        "--resolve-after",
        action="store_true",
        help="Mark intervention as resolved after Claude Code exits"
    )

    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    context = None
    task_type = None
    url = None

    if args.intervention:
        print(f"Fetching intervention {args.intervention}...")
        context = await get_intervention_context(args.intervention)
        if not context:
            print("Failed to fetch intervention context")
            return 1
        task_type = "intervention"
        url = context.get("current_url")

    elif args.session:
        print(f"Fetching session {args.session}...")
        context = await get_session_context(args.session)
        if not context:
            print("Failed to fetch session context")
            return 1
        task_type = "session"
        url = context.get("current_url") or context.get("job_url")

    elif args.url:
        context = {"url": args.url, "task": args.task}
        task_type = "direct"
        url = args.url

    else:
        parser.print_help()
        return 1

    # Generate prompt
    prompt = generate_claude_prompt(context, task_type)

    # Write context file
    context_file = create_claude_context_file(prompt, output_path)
    print(f"\nContext saved to: {context_file}")

    # Launch Claude Code
    if not args.no_launch:
        success = launch_claude_code(context_file, url)

        if success and args.resolve_after and args.intervention:
            input("\nPress Enter after completing the intervention to mark it as resolved...")
            await resolve_intervention(args.intervention)
    else:
        print("\n--no-launch specified. Context file created.")
        print("Run Claude Code manually with this context.")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
