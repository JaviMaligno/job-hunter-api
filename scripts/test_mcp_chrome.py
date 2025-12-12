#!/usr/bin/env python
"""Test script for Chrome DevTools MCP client."""

import asyncio
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_snapshot_for_elements(snapshot_text: str) -> list[dict]:
    """Parse snapshot markdown to extract elements with UIDs.

    The snapshot format is:
    uid=1_0 RootWebArea "Example Domain" url="https://example.com/"
      uid=1_1 heading "Example Domain" level="1"
      uid=1_2 StaticText "Some text"
      uid=1_3 link "Learn more" url="..."
    """
    elements = []
    # Pattern to match uid=X_Y followed by role and optional name
    # uid=2_5 link "Aceptar" url="javascript: void(0)"
    pattern = r'uid=(\d+_\d+)\s+(\w+)(?:\s+"([^"]*)")?'

    for match in re.finditer(pattern, snapshot_text):
        uid = match.group(1)
        role = match.group(2)
        name = match.group(3) or ""
        elements.append({
            "uid": uid,
            "role": role,
            "name": name,
        })

    return elements


def find_element_by_name(elements: list[dict], name_contains: str) -> dict | None:
    """Find element whose name contains the given string."""
    for el in elements:
        if name_contains.lower() in el.get("name", "").lower():
            return el
    return None


def find_element_by_role(elements: list[dict], role: str, name_contains: str = "") -> dict | None:
    """Find element by role and optionally name."""
    for el in elements:
        if el.get("role", "").lower() == role.lower():
            if not name_contains or name_contains.lower() in el.get("name", "").lower():
                return el
    return None


def find_all_by_role(elements: list[dict], role: str) -> list[dict]:
    """Find all elements with given role."""
    return [el for el in elements if el.get("role", "").lower() == role.lower()]


async def test_mcp_connection():
    """Test basic MCP connection and tool listing."""
    from src.mcp.chrome_client import ChromeDevToolsMCP

    logger.info("Testing Chrome DevTools MCP connection...")

    try:
        async with ChromeDevToolsMCP() as chrome:
            # List available tools
            tools = await chrome.list_available_tools()
            logger.info(f"Available tools ({len(tools)}): {tools}")

            # Navigate to a simple page
            logger.info("Navigating to example.com...")
            result = await chrome.navigate("https://example.com")
            logger.info(f"Navigate result: {result.get('text', '')[:100]}...")

            # Get page title (properly parsed)
            title = await chrome.get_page_title()
            logger.info(f"Page title: '{title}'")

            # Get current URL (properly parsed)
            url = await chrome.get_current_url()
            logger.info(f"Current URL: '{url}'")

            # Take accessibility snapshot
            logger.info("\n--- Taking accessibility snapshot ---")
            snapshot = await chrome.take_snapshot()
            snapshot_text = snapshot.get("text", "")
            logger.info(f"Snapshot length: {len(snapshot_text)} chars")

            # Parse elements from snapshot
            elements = parse_snapshot_for_elements(snapshot_text)
            logger.info(f"Found {len(elements)} elements in snapshot:")
            for el in elements[:10]:
                logger.info(f"  - uid={el['uid']} {el['role']}: \"{el['name']}\"")

            # Test click on the "More information" link
            link_el = find_element_by_role(elements, "link")
            if link_el:
                logger.info(f"\nFound link: uid={link_el['uid']} '{link_el['name']}'")
                click_result = await chrome.click(link_el['uid'])
                logger.info(f"Click result: {click_result}")

                # Wait for navigation
                await asyncio.sleep(2)

                # Get new page info
                new_title = await chrome.get_page_title()
                new_url = await chrome.get_current_url()
                logger.info(f"After click - Title: '{new_title}', URL: '{new_url}'")

            # Take a screenshot
            logger.info("\n--- Taking screenshot ---")
            screenshot = await chrome.screenshot()
            has_data = "data" in screenshot or "text" in screenshot
            logger.info(f"Screenshot captured: {has_data}")

            # Navigate to Google (simpler than Bing)
            logger.info("\n--- Testing with Google search page ---")
            await chrome.navigate("https://www.google.com")
            await asyncio.sleep(2)  # Wait for page to load

            # Take snapshot of Google
            google_snapshot = await chrome.take_snapshot()
            google_snapshot_text = google_snapshot.get("text", "")
            logger.info(f"Google snapshot:\n{google_snapshot_text[:1500]}...")

            # Parse elements
            google_elements = parse_snapshot_for_elements(google_snapshot_text)
            logger.info(f"\nFound {len(google_elements)} elements on Google")

            # Show all element types
            roles = {}
            for el in google_elements:
                role = el.get("role", "unknown")
                if role not in roles:
                    roles[role] = []
                roles[role].append(el)

            logger.info("Elements by role:")
            for role, els in sorted(roles.items()):
                logger.info(f"  {role}: {len(els)} elements")
                for el in els[:2]:
                    logger.info(f"    - uid={el['uid']} \"{el['name'][:50]}...\"" if len(el['name']) > 50 else f"    - uid={el['uid']} \"{el['name']}\"")

            # Find search box (combobox or textbox with "search" in name)
            search_candidates = [el for el in google_elements
                                if el.get("role", "").lower() in ("combobox", "textbox", "searchbox")
                                or "search" in el.get("name", "").lower()]
            logger.info(f"\nSearch candidates: {search_candidates}")

            if search_candidates:
                search_box = search_candidates[0]
                logger.info(f"Using search box: uid={search_box['uid']} {search_box['role']}: \"{search_box['name']}\"")

                # Fill the search box
                logger.info("Filling search box with 'MCP browser automation'...")
                fill_result = await chrome.fill(search_box["uid"], "MCP browser automation")
                logger.info(f"Fill result: {fill_result}")

                # Take screenshot after fill
                await asyncio.sleep(1)
                await chrome.screenshot()
                logger.info("Screenshot taken after fill")

            logger.info("\n=== MCP test completed successfully! ===")
            return True

    except Exception as e:
        logger.error(f"MCP test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_mcp_connection())
    exit(0 if success else 1)
