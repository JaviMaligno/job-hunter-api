"""Test browser service client."""

import asyncio


async def test():
    from src.automation.client import BrowserServiceClient
    from src.browser_service.models import BrowserMode

    print("Starting test...", flush=True)

    try:
        async with BrowserServiceClient(
            base_url="https://job-hunter-browser-service.onrender.com"
        ) as client:
            print("Creating session...", flush=True)
            session = await client.create_session(mode=BrowserMode.PLAYWRIGHT, headless=True)
            print(f"Session created: {session.session_id}", flush=True)

            print("Closing session...", flush=True)
            await client.close_session()
            print("Done!", flush=True)
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())
