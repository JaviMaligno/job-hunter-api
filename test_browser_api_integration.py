"""Test browser API integration - simpler test for Render free tier."""
import asyncio
from src.automation.client import BrowserServiceClient
from src.config import settings

BROWSER_SERVICE_URL = settings.browser_service_url


async def test_browser_integration():
    """Test browser service integration from API."""
    print("=" * 60)
    print("BROWSER API INTEGRATION TEST")
    print("=" * 60)
    print(f"Browser Service URL: {BROWSER_SERVICE_URL}")
    print()

    # 1. Check service availability
    print("1. Checking service availability...")
    available = await BrowserServiceClient.is_service_available(BROWSER_SERVICE_URL)
    print(f"   Available: {available}")
    if not available:
        print("   FAILED: Browser service not available")
        return False
    print()

    # 2. Use the client
    print("2. Testing BrowserServiceClient...")
    async with BrowserServiceClient(base_url=BROWSER_SERVICE_URL, timeout=120.0) as client:
        # Health check
        print("   a) Health check...")
        health = await client.health_check()
        print(f"      Status: {health['status']}")
        print(f"      Active sessions: {health['active_sessions']}")

        # Create session
        print("   b) Creating session...")
        session = await client.create_session(headless=True)
        print(f"      Session ID: {session.session_id}")
        print(f"      Mode: {session.mode}")

        # Navigate to simple page
        print("   c) Navigating to example.com...")
        nav = await client.navigate("https://example.com", wait_until="domcontentloaded")
        print(f"      Success: {nav.success}")
        print(f"      URL: {nav.url}")
        print(f"      Duration: {nav.duration_ms}ms")

        # Get DOM
        print("   d) Getting DOM...")
        dom = await client.get_dom()
        print(f"      Page URL: {dom.page_url}")
        print(f"      Page Title: {dom.page_title}")
        print(f"      Form Fields: {len(dom.form_fields)}")

        # Take screenshot
        print("   e) Taking screenshot...")
        screenshot = await client.screenshot()
        print(f"      Success: {screenshot.success}")
        if screenshot.screenshot_base64:
            print(f"      Size: {len(screenshot.screenshot_base64)} chars")

    print()
    print("=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys
    success = asyncio.run(test_browser_integration())
    sys.exit(0 if success else 1)
