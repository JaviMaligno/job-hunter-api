"""Test full job application automation flow using the API."""
import asyncio
import json
import httpx

API_URL = "http://localhost:8000"
BROWSER_SERVICE_URL = "https://job-hunter-browser-service.onrender.com"

# Test user data
TEST_USER_DATA = {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john.doe@example.com",
    "phone": "555-1234567",
    "phone_country_code": "+1",
    "linkedin_url": "https://linkedin.com/in/johndoe",
    "github_url": "https://github.com/johndoe",
    "city": "New York",
    "country": "United States",
    "postal_code": "10001",
}

# Test CV content
TEST_CV_CONTENT = """
JOHN DOE
Software Engineer

CONTACT
Email: john.doe@example.com
Phone: +1 555-1234567
LinkedIn: linkedin.com/in/johndoe
GitHub: github.com/johndoe

SUMMARY
Experienced software engineer with 5+ years of experience in full-stack development.
Proficient in Python, TypeScript, React, and cloud technologies.

EXPERIENCE
Senior Software Engineer | Tech Company | 2020-Present
- Developed and maintained microservices architecture
- Led team of 4 developers
- Implemented CI/CD pipelines

Software Engineer | Startup Inc | 2018-2020
- Built React applications from scratch
- Designed RESTful APIs
- Worked with PostgreSQL and MongoDB

EDUCATION
B.S. Computer Science | University | 2018

SKILLS
Languages: Python, TypeScript, JavaScript, SQL
Frameworks: FastAPI, React, Next.js, Django
Cloud: AWS, GCP, Docker, Kubernetes
"""

# Test job URL - using simple example page for testing
# httpbin is too slow on Render free tier
TEST_JOB_URL = "https://example.com"


async def test_job_application_flow():
    """Test the full job application automation flow."""
    print("=" * 60)
    print("JOB APPLICATION AUTOMATION FLOW TEST")
    print("=" * 60)
    print()

    async with httpx.AsyncClient(base_url=API_URL, timeout=120.0) as client:
        # 1. Check API health
        print("1. Checking API health...")
        try:
            resp = await client.get("/health")
            if resp.status_code == 200:
                print(f"   API Status: {resp.json()}")
            else:
                print(f"   API returned: {resp.status_code}")
        except Exception as e:
            print(f"   ERROR: {e}")
            return

        # 2. Check browser service connectivity via API
        print()
        print("2. Checking browser service connectivity...")
        try:
            # Direct check to browser service
            async with httpx.AsyncClient(timeout=30.0) as browser_client:
                resp = await browser_client.get(f"{BROWSER_SERVICE_URL}/health")
                print(f"   Browser Service: {resp.json()}")
        except Exception as e:
            print(f"   WARNING connecting to browser service: {e}")
            print("   Continuing anyway (API will handle connection)...")

        # 3. Start job application with Claude agent
        print()
        print("3. Starting job application automation...")
        print(f"   Job URL: {TEST_JOB_URL}")
        print(f"   Agent: claude")
        print(f"   Mode: assisted")

        request_body = {
            "job_url": TEST_JOB_URL,
            "user_data": TEST_USER_DATA,
            "cv_content": TEST_CV_CONTENT,
            "mode": "assisted",
            "agent": "claude",
            "browser_mode": "playwright",  # Use Playwright on Render
        }

        print()
        print("   Sending request to /api/applications/v2/start...")

        try:
            resp = await client.post(
                "/api/applications/v2/start",
                json=request_body,
            )

            print(f"   Status Code: {resp.status_code}")

            if resp.status_code == 200:
                result = resp.json()
                print()
                print("   RESULT:")
                print(f"   - Session ID: {result.get('session_id')}")
                print(f"   - Status: {result.get('status')}")
                print(f"   - Success: {result.get('success')}")
                print(f"   - Agent Used: {result.get('agent_used')}")
                print(f"   - Steps Completed: {result.get('steps_completed')}")
                print(f"   - Fields Filled: {result.get('fields_filled')}")
                print(f"   - Final URL: {result.get('final_url')}")

                if result.get("intervention_id"):
                    print(f"   - Intervention ID: {result.get('intervention_id')}")
                    print(f"   - Intervention Type: {result.get('intervention_type')}")
                    print(f"   - Intervention Title: {result.get('intervention_title')}")

                if result.get("error"):
                    print(f"   - ERROR: {result.get('error')}")

            else:
                print(f"   Response: {resp.text[:500]}")

        except Exception as e:
            print(f"   ERROR: {e}")
            import traceback
            traceback.print_exc()

        # 4. Get session details
        print()
        print("4. Fetching session list...")
        try:
            resp = await client.get("/api/applications/v2/sessions")
            if resp.status_code == 200:
                sessions = resp.json()
                print(f"   Total sessions: {len(sessions)}")
                for s in sessions[:3]:
                    print(f"   - {s['session_id'][:8]}... | {s['status']} | {s['fields_filled']} fields")
        except Exception as e:
            print(f"   ERROR: {e}")

    print()
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_job_application_flow())
