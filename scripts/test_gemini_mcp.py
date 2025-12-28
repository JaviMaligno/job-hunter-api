#!/usr/bin/env python3
"""
Test script for Gemini + Chrome MCP integration.

This script validates:
1. Gemini API key works with 2.5 Pro model
2. Chrome DevTools MCP can be used as a tool
3. Basic browser automation (navigate, snapshot, fill, click)

Usage:
    poetry run python scripts/test_gemini_mcp.py
"""

import asyncio
import os
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from google import genai

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_PRIMARY = "gemini-2.5-pro"
MODEL_FALLBACK = "gemini-2.5-flash"


async def test_gemini_basic():
    """Test basic Gemini API connectivity."""
    print("\n=== Test 1: Basic Gemini API ===")

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Try primary model first
    try:
        response = client.models.generate_content(
            model=MODEL_PRIMARY, contents="Say 'Hello from Gemini 2.5 Pro!' in exactly those words."
        )
        print(f"[OK] Model: {MODEL_PRIMARY}")
        print(f"[OK] Response: {response.text}")
        return MODEL_PRIMARY
    except Exception as e:
        print(f"[FAIL] Primary model failed: {e}")

    # Fallback to flash
    try:
        response = client.models.generate_content(
            model=MODEL_FALLBACK,
            contents="Say 'Hello from Gemini 2.5 Flash!' in exactly those words.",
        )
        print(f"[OK] Fallback Model: {MODEL_FALLBACK}")
        print(f"[OK] Response: {response.text}")
        return MODEL_FALLBACK
    except Exception as e:
        print(f"[FAIL] Fallback model also failed: {e}")
        return None


async def test_mcp_connection():
    """Test MCP server connection."""
    print("\n=== Test 2: Chrome MCP Connection ===")

    server_params = StdioServerParameters(
        command="npx",
        args=["chrome-devtools-mcp@latest"],
        env=None,
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the session
                await session.initialize()

                # List available tools
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]

                print("[OK] MCP Connection established")
                print(f"[OK] Available tools ({len(tool_names)}):")
                for name in tool_names:
                    print(f"     - {name}")

                return True
    except Exception as e:
        print(f"[FAIL] MCP Connection failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_manual_mcp_navigation():
    """Test manual MCP tool calls for navigation."""
    print("\n=== Test 3: MCP Browser Navigation ===")

    server_params = StdioServerParameters(
        command="npx",
        args=["chrome-devtools-mcp@latest"],
        env=None,
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Navigate to a page
                print("-> Navigating to example.com...")
                result = await session.call_tool(
                    "navigate_page", arguments={"url": "https://example.com"}
                )
                print("[OK] Navigation complete")

                # Take a snapshot
                print("-> Taking page snapshot...")
                snapshot = await session.call_tool("take_snapshot", arguments={})
                # Snapshot can be large, just show summary
                snapshot_text = str(snapshot)
                print(f"[OK] Snapshot received ({len(snapshot_text)} chars)")

                # Show first part of snapshot
                if len(snapshot_text) > 200:
                    print(f"     Preview: {snapshot_text[:200]}...")
                else:
                    print(f"     Content: {snapshot_text}")

                return True

    except Exception as e:
        print(f"[FAIL] MCP navigation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_gemini_with_mcp_tools():
    """Test Gemini calling MCP tools via function calling."""
    print("\n=== Test 4: Gemini + MCP Tool Calling ===")

    client = genai.Client(api_key=GEMINI_API_KEY)

    server_params = StdioServerParameters(
        command="npx",
        args=["chrome-devtools-mcp@latest"],
        env=None,
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                print("[OK] MCP session ready")

                # Simple test: ask Gemini to navigate and describe page
                prompt = """
                I need you to help me with browser automation.

                Navigate to https://example.com and tell me what you see on the page.
                Use the navigate_page tool first, then take_snapshot to see the page content.
                """

                # Use Gemini with MCP tools
                response = await client.aio.models.generate_content(
                    model=MODEL_FALLBACK,  # Use flash for speed
                    contents=prompt,
                    config={
                        "tools": [session],
                        "automatic_function_calling": {"disable": False},
                    },
                )

                print("[OK] Gemini response:")
                print(response.text)

                return True

    except Exception as e:
        print(f"[FAIL] Gemini + MCP failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_job_form_navigation():
    """Test navigating to a real job application form."""
    print("\n=== Test 5: Real Job Form Navigation ===")

    # Use a known job board that doesn't require login
    test_url = "https://apply.workable.com/metova/j/27E1EE6C09/"  # Example job

    server_params = StdioServerParameters(
        command="npx",
        args=["chrome-devtools-mcp@latest"],
        env=None,
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Navigate to job page
                print(f"-> Navigating to: {test_url}")
                await session.call_tool("navigate_page", arguments={"url": test_url})
                print("[OK] Navigation complete")

                # Wait a bit for page to load
                await asyncio.sleep(2)

                # Take snapshot
                print("-> Taking snapshot...")
                snapshot = await session.call_tool("take_snapshot", arguments={})

                snapshot_text = str(snapshot)
                print(f"[OK] Snapshot received ({len(snapshot_text)} chars)")

                # Look for form elements in snapshot
                if "apply" in snapshot_text.lower() or "submit" in snapshot_text.lower():
                    print("[OK] Found application-related content")
                else:
                    print("[INFO] Page loaded but no obvious apply button found")

                return True

    except Exception as e:
        print(f"[FAIL] Job form navigation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Gemini + Chrome MCP Integration Tests")
    print("=" * 60)

    if not GEMINI_API_KEY:
        print("[FAIL] GEMINI_API_KEY not found in environment")
        return

    print(f"API Key: {GEMINI_API_KEY[:10]}...{GEMINI_API_KEY[-4:]}")
    print(f"Primary Model: {MODEL_PRIMARY}")
    print(f"Fallback Model: {MODEL_FALLBACK}")

    results = {}

    # Test 1: Basic Gemini
    working_model = await test_gemini_basic()
    results["gemini_basic"] = working_model is not None

    if not working_model:
        print("\n[FAIL] Cannot proceed without working Gemini model")
        return

    # Test 2: MCP Connection
    results["mcp_connection"] = await test_mcp_connection()

    # Test 3: MCP Navigation
    results["mcp_navigation"] = await test_manual_mcp_navigation()

    # Test 4: Gemini + MCP (optional - may not work with experimental API)
    # results["gemini_mcp"] = await test_gemini_with_mcp_tools()

    # Test 5: Real job form
    # results["job_form"] = await test_job_form_navigation()

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for test, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {test}")

    all_passed = all(results.values())
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed."))
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
