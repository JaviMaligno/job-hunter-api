#!/usr/bin/env python3
"""
Test form automation with Gemini + Chrome MCP.

This script tests real job application form filling.

Usage:
    poetry run python scripts/test_form_automation.py
"""

import asyncio
import json
import os
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv

load_dotenv()

from google import genai
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-2.5-flash"

# Test user data
TEST_USER = {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "phone": "+44 7700 900123",
    "linkedin_url": "https://linkedin.com/in/johndoe",
}

# Test job URL (Breezy - known to work from POC)
TEST_JOB_URL = "https://soulchi.breezy.hr/p/d6f51a0ba0a8-full-stack-developer"


async def run_automation_with_gemini():
    """Use Gemini to orchestrate the form filling."""
    print("\n=== Form Automation with Gemini ===\n")

    client = genai.Client(api_key=GEMINI_API_KEY)

    server_params = StdioServerParameters(
        command="npx",
        args=["chrome-devtools-mcp@latest"],
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()

            tools = await mcp.list_tools()
            print(f"[OK] MCP ready with {len(tools.tools)} tools")

            # Step 1: Navigate to job page
            print(f"\n-> Step 1: Navigate to {TEST_JOB_URL}")
            try:
                await mcp.call_tool("navigate_page", {"url": TEST_JOB_URL})
                print("[OK] Navigation initiated")

                # Wait for page load
                await asyncio.sleep(3)

                # Get snapshot to see what's on page
                snapshot = await mcp.call_tool("take_snapshot", {})
                snapshot_text = str(snapshot)
                print(f"[OK] Page loaded ({len(snapshot_text)} chars)")

                # Check for error
                if "chrome-error" in snapshot_text.lower():
                    print("[WARN] Chrome error detected - might need Chrome to be running")
                    print("       Snapshot preview:", snapshot_text[:300])
                    return False

            except Exception as e:
                print(f"[FAIL] Navigation error: {e}")
                return False

            # Step 2: Analyze the page with Gemini
            print("\n-> Step 2: Analyze page with Gemini")

            analysis_prompt = f"""
            Analyze this page snapshot and identify:
            1. Is this a job application form?
            2. What form fields are visible?
            3. Are there any blockers (CAPTCHA, login required)?

            Page snapshot:
            {snapshot_text[:5000]}
            """

            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=analysis_prompt
                )
                print("[OK] Gemini analysis:")
                print(response.text[:500])
            except Exception as e:
                print(f"[FAIL] Gemini analysis error: {e}")
                return False

            # Step 3: Look for Apply button and click it
            print("\n-> Step 3: Find and click Apply button")

            # Search for apply button in snapshot
            if "apply" in snapshot_text.lower():
                print("[OK] Found 'apply' text in page")

                # Use Gemini to find the button uid
                find_button_prompt = f"""
                In this accessibility snapshot, find the UID of the "Apply" or "Apply Now" button.
                Return ONLY the uid value (like "1_5" or "2_3"), nothing else.

                Snapshot:
                {snapshot_text[:3000]}
                """

                try:
                    button_response = client.models.generate_content(
                        model=MODEL,
                        contents=find_button_prompt
                    )
                    button_uid = button_response.text.strip()
                    print(f"[OK] Button UID identified: {button_uid}")

                    # Click the button
                    if button_uid and "_" in button_uid:
                        await mcp.call_tool("click", {"uid": button_uid})
                        print("[OK] Clicked apply button")
                        await asyncio.sleep(2)

                        # Get new snapshot
                        new_snapshot = await mcp.call_tool("take_snapshot", {})
                        print(f"[OK] New page state captured")
                    else:
                        print(f"[WARN] Invalid button UID: {button_uid}")

                except Exception as e:
                    print(f"[FAIL] Button click error: {e}")

            else:
                print("[INFO] No 'apply' text found - might already be on form")

            # Step 4: Fill form fields
            print("\n-> Step 4: Fill form fields")

            # Get fresh snapshot
            snapshot = await mcp.call_tool("take_snapshot", {})
            snapshot_text = str(snapshot)

            # Use Gemini to identify form fields and their UIDs
            form_fields_prompt = f"""
            In this accessibility snapshot, identify form input fields and their UIDs.
            For each field found, return a JSON array with objects containing:
            - uid: the element UID
            - field_type: "first_name", "last_name", "email", "phone", or "other"
            - label: the field label or placeholder

            Return ONLY valid JSON, no markdown or explanation.

            Snapshot:
            {snapshot_text[:5000]}
            """

            try:
                fields_response = client.models.generate_content(
                    model=MODEL,
                    contents=form_fields_prompt
                )
                fields_text = fields_response.text.strip()

                # Clean up JSON
                if fields_text.startswith("```"):
                    fields_text = fields_text.split("```")[1]
                    if fields_text.startswith("json"):
                        fields_text = fields_text[4:]

                print(f"[OK] Gemini identified fields:")
                print(fields_text[:500])

                # Try to parse and fill fields
                try:
                    fields = json.loads(fields_text)
                    for field in fields:
                        uid = field.get("uid")
                        field_type = field.get("field_type", "").lower()

                        value = None
                        if field_type == "first_name":
                            value = TEST_USER["first_name"]
                        elif field_type == "last_name":
                            value = TEST_USER["last_name"]
                        elif field_type == "email":
                            value = TEST_USER["email"]
                        elif field_type == "phone":
                            value = TEST_USER["phone"]

                        if value and uid:
                            print(f"     Filling {field_type} ({uid}) = {value}")
                            await mcp.call_tool("fill", {"uid": uid, "value": value})
                            await asyncio.sleep(0.5)

                except json.JSONDecodeError:
                    print("[WARN] Could not parse field JSON")

            except Exception as e:
                print(f"[FAIL] Form filling error: {e}")

            # Step 5: Take final screenshot
            print("\n-> Step 5: Take screenshot of result")
            try:
                screenshot = await mcp.call_tool("take_screenshot", {})
                print("[OK] Screenshot taken")
            except Exception as e:
                print(f"[WARN] Screenshot error: {e}")

            print("\n[DONE] Automation test complete")
            return True


async def test_simple_navigation():
    """Test simple navigation without Gemini."""
    print("\n=== Simple Navigation Test ===\n")

    server_params = StdioServerParameters(
        command="npx",
        args=["chrome-devtools-mcp@latest"],
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()

            # First create a new page
            print("-> Creating new page...")
            try:
                result = await mcp.call_tool("new_page", {})
                print(f"[OK] New page: {result}")
            except Exception as e:
                print(f"[INFO] new_page result: {e}")

            # List pages
            print("-> Listing pages...")
            pages = await mcp.call_tool("list_pages", {})
            print(f"[OK] Pages: {pages}")

            # Navigate
            print(f"-> Navigating to {TEST_JOB_URL}...")
            await mcp.call_tool("navigate_page", {"url": TEST_JOB_URL})

            # Wait
            print("-> Waiting for page load...")
            await asyncio.sleep(5)

            # Snapshot
            print("-> Taking snapshot...")
            snapshot = await mcp.call_tool("take_snapshot", {})
            snapshot_text = str(snapshot)

            print(f"[OK] Snapshot ({len(snapshot_text)} chars):")
            print(snapshot_text[:1000])

            return "chrome-error" not in snapshot_text.lower()


async def main():
    print("=" * 60)
    print("Job Form Automation Test")
    print("=" * 60)

    # Test 1: Simple navigation
    nav_ok = await test_simple_navigation()

    if nav_ok:
        # Test 2: Full automation with Gemini
        await run_automation_with_gemini()
    else:
        print("\n[FAIL] Navigation not working - check Chrome setup")
        print("       Make sure Chrome is installed and accessible")


if __name__ == "__main__":
    asyncio.run(main())
