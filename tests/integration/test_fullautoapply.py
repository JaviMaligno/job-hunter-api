"""Test Full Auto Apply mode."""
import httpx
import json
import time
import sys

BASE_URL = "http://localhost:8000"

def main():
    print("Starting Full Auto Apply test...")

    # Step 1: Register/Login
    print("\n1. Registering user...")
    r = httpx.post(f"{BASE_URL}/api/auth/register", json={
        "email": "fullauto5@example.com",
        "password": "Test123!",
        "first_name": "Full",
        "last_name": "AutoTester"
    }, timeout=10.0)

    if r.status_code in [400, 422] and ("already registered" in r.text or "already exists" in r.text.lower()):
        print("   User exists, logging in...")
        r = httpx.post(f"{BASE_URL}/api/auth/login", json={
            "email": "fullauto5@example.com",
            "password": "Test123!"
        }, timeout=10.0)

    print(f"   Status: {r.status_code}")
    data = r.json()

    if "access_token" not in data:
        print(f"   Error: {data}")
        sys.exit(1)

    token = data["access_token"]
    user_id = data["user"]["id"]
    print(f"   Token obtained for user: {user_id}")

    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Import a job (using Greenhouse which is accessible)
    print("\n2. Importing Greenhouse job for test...")
    greenhouse_url = "https://boards.greenhouse.io/anthropic/jobs/4112015008"
    r = httpx.post(
        f"{BASE_URL}/api/jobs/import-url?user_id={user_id}&skip_scraping=true",
        json={"url": greenhouse_url},
        headers=headers,
        timeout=30.0,
        follow_redirects=True
    )
    print(f"   Import status: {r.status_code}")

    if r.status_code in [200, 201]:
        job = r.json().get("job")
        if job:
            print(f"   Imported: {job.get('title')} at {job.get('company')}")
    else:
        # Try to get existing jobs
        print(f"   Import response: {r.text[:200]}")
        print("   Trying to get existing jobs instead...")
        r = httpx.get(f"{BASE_URL}/api/jobs/?user_id={user_id}&page_size=5", headers=headers, timeout=10.0, follow_redirects=True)
        if r.status_code != 200:
            print(f"   Error getting jobs: {r.text}")
            sys.exit(1)

        response_data = r.json()
        jobs = response_data.get("jobs", response_data) if isinstance(response_data, dict) else response_data

        if not jobs:
            print("   No jobs found!")
            sys.exit(1)

        # Find a Greenhouse job (more likely to work)
        job = None
        for j in jobs:
            if "greenhouse" in j.get("source_url", "").lower():
                job = j
                break
        if not job:
            job = jobs[0]

    print(f"   Selected job: {job['title']} at {job.get('company', 'Unknown')}")
    job_url = job.get('source_url') or job.get('url')
    print(f"   URL: {job_url}")

    # Step 3: Start Full Auto application
    print("\n3. Starting FULL AUTO application...")

    # Prepare user data for form filling
    user_form_data = {
        "first_name": "Full",
        "last_name": "AutoTester",
        "email": "fullauto5@example.com",
        "phone": "+1234567890",
        "phone_country_code": "+1",
        "linkedin_url": "https://linkedin.com/in/fullauto",
        "city": "New York",
        "country": "United States"
    }

    # Sample CV content
    cv_content = """
    FULL AUTOTESTER
    Software Engineer | fullauto5@example.com | +1234567890

    EXPERIENCE
    Senior Software Engineer - TechCorp (2020-Present)
    - Developed scalable microservices using Python and FastAPI
    - Led team of 5 engineers on critical infrastructure projects
    - Improved system performance by 40%

    Software Engineer - StartupXYZ (2018-2020)
    - Built RESTful APIs and web applications
    - Implemented CI/CD pipelines using GitHub Actions

    EDUCATION
    B.S. Computer Science - MIT (2018)

    SKILLS
    Python, FastAPI, PostgreSQL, Docker, Kubernetes, AWS
    """

    r = httpx.post(
        f"{BASE_URL}/api/applications/v2/start",
        json={
            "job_url": job_url,
            "user_data": user_form_data,
            "cv_content": cv_content,
            "mode": "auto",  # Full auto mode
            "agent": "claude",  # Use Claude agent (Gemini needs extra setup)
            "auto_solve_captcha": False  # Don't try to solve CAPTCHAs automatically
        },
        headers=headers,
        timeout=120.0,  # Longer timeout for application
        follow_redirects=True
    )

    print(f"   Status: {r.status_code}")
    result = r.json()
    print(f"   Response: {json.dumps(result, indent=2)}")

    session_id = result.get("session_id")
    if not session_id:
        print("   No session ID returned!")
        sys.exit(1)

    # Step 4: Poll for status (full auto should complete on its own)
    print("\n4. Polling application status...")
    max_polls = 30
    for i in range(max_polls):
        time.sleep(2)
        r = httpx.get(
            f"{BASE_URL}/api/applications/{session_id}/status",
            headers=headers,
            timeout=10.0,
            follow_redirects=True
        )
        status_data = r.json()
        status = status_data.get("status", "unknown")
        print(f"   Poll {i+1}: status={status}")

        if status in ["completed", "failed", "needs_intervention"]:
            print(f"\n5. Final result:")
            print(json.dumps(status_data, indent=2))
            break
    else:
        print("   Timeout waiting for completion!")

    print("\nTest completed!")

if __name__ == "__main__":
    main()
