#!/usr/bin/env python3
"""
Real E2E Test for Job Application Automation.

This script tests the full automation flow with real user data and a real job URL.
"""

import asyncio
import httpx
import json
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

API_URL = "http://localhost:8000"

# Real user data from database
USER_DATA = {
    "first_name": "Javier",
    "last_name": "Aguilar Martín",
    "email": "javiecija96@gmail.com",
    "phone": "+34 612 345 678",
    "phone_country_code": "+34",
    "linkedin_url": "https://linkedin.com/in/javieralvarez",
    "github_url": "https://github.com/javieralvarez",
    "country": "Spain",
    "city": "Seville",
}

# Real CV content from database
CV_CONTENT = """CURRICULUM VITAE

Personal Data:

- Last Name: Aguilar Martín
- First Name: Javier
- Birth: April 5th 1996
- Nationality: Spanish
- Address: 62 Rushmead Close, CT2 7RP, Canterbury (Kent), UK
- Phone number: +44 07419 682007
- E-mail: javiecija96@gmail.com
- GitHub: https://github.com/JaviMaligno

Academic Training:

2020 – 2023               PhD in Mathematics (University of Kent)
2018 – 2019              Master's Degree in Mathematics (University of Seville)
2014 – 2018               Degree in Mathematics (University of Seville)

Experience:

• Freelance Data Scientist for SimpleKYC (2024 – Present)
o Data Analysis
o Data Cleansing
o Data pipelines
o MySQL
o ElasticSearch
o Bigquery
o Excel
o Google Cloud
o Bash scripting
o Automation
o Python scripting
o Git
o BitBucket

• Graduate Data Scientist for Hastings Direct (2023 – Present)
o Data Modelling
o GLMs in Emblem
o GBMs in Python
o Data Wrangling
o Snowflake
o Databricks
o AzureML
o Automation
o Excel
o Git
o GitHub

• Online Data Analyst for TELUS International (2022 – 2023)
o Query analysis
o Customer satisfaction

• Graduate Teaching Assistant for the University of Kent (2020 – 2023)
o Teaching
o Statistical analysis
o Neural networks in python with tensorflow
o Task automation

• Graduate Teaching Assistant for King's College London (2020 – 2023)
o Teaching
o Research
o Technical writing

• Junior Python Developer for Everis NTT Data (2021)
o Backend development
o Python scripting
o Excel
o Git
o GitLab

Technical skills:

• Fluency programming in Python, Matlab and R.
• Mathematical modelling experience in insurance with Python GBMs and Emblem GLMs.
• Experience with relational databases (MySQL, SQLite, Snowflake) and NoSQL databases
(MongoDB, ElasticSearch).
• Experience using Git and cloud environments such as Databricks, Azure ML and Google
Cloud
• Understanding of HTTP Requests and RESTful API's.
• Exposure to technologies like Docker and Kubernetes.

Languages:

Spanish: Native
English: Advanced
German: B2
French: B1

Personal skills:

• Experience in teaching and communicating complex information to various audiences.
• Ability to analyze and solve problems finding original solutions.
• Ability to work independently under my own initiative as well as collaboratively in group.
"""

# Test job URLs
TEST_JOBS = [
    {
        "name": "Greenhouse (Anthropic)",
        "url": "https://boards.greenhouse.io/anthropic/jobs/4112015008",
    },
    {
        "name": "BambooHR (Abstra)",
        "url": "https://abstra.bamboohr.com/careers/123",
    },
    {
        "name": "Workable Demo",
        "url": "https://apply.workable.com/workable-1/j/D0D6B8F5FA/",
    },
]


async def test_v2_start(job_url: str, agent: str = "gemini"):
    """Test the v2/start endpoint with real data."""
    print(f"\n{'='*60}")
    print(f"Testing V2 Application Start")
    print(f"Job URL: {job_url}")
    print(f"Agent: {agent}")
    print(f"{'='*60}\n")

    request_data = {
        "job_url": job_url,
        "user_data": USER_DATA,
        "cv_content": CV_CONTENT,
        "agent": agent,
        "auto_solve_captcha": True,
        "max_steps": 20,
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            print("Sending request to /api/applications/v2/start...")
            print(f"User: {USER_DATA['first_name']} {USER_DATA['last_name']}")
            print(f"Email: {USER_DATA['email']}")
            print()

            response = await client.post(
                f"{API_URL}/api/applications/v2/start",
                json=request_data,
            )

            print(f"Status Code: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print(f"\n✅ SUCCESS!")
                print(f"Session ID: {result.get('session_id')}")
                print(f"Status: {result.get('status')}")
                print(f"Agent Used: {result.get('agent_used')}")
                print(f"Current URL: {result.get('current_url')}")

                if result.get('fields_filled'):
                    print(f"\nFields Filled ({len(result['fields_filled'])}):")
                    for field in result['fields_filled'][:5]:
                        print(f"  - {field.get('field_name')}: {field.get('value')[:50]}...")

                if result.get('intervention_required'):
                    print(f"\n⚠️ INTERVENTION REQUIRED")
                    print(f"Intervention ID: {result.get('intervention_id')}")
                    print(f"Blocker Type: {result.get('blocker_type')}")
                    print(f"Blocker Details: {result.get('blocker_details')}")

                return result
            else:
                print(f"\n❌ ERROR: {response.status_code}")
                print(response.text)
                return None

        except httpx.TimeoutException:
            print("❌ Request timed out (this is normal for long operations)")
            return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None


async def list_sessions():
    """List all active sessions."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}/api/applications/v2/sessions")
        if response.status_code == 200:
            sessions = response.json()
            print(f"\nActive Sessions ({len(sessions)}):")
            for s in sessions:
                print(f"  - {s['session_id'][:8]}... | {s['status']} | {s['job_url'][:50]}...")
            return sessions
        return []


async def list_interventions():
    """List pending interventions."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}/api/applications/v2/interventions")
        if response.status_code == 200:
            interventions = response.json()
            print(f"\nPending Interventions ({len(interventions)}):")
            for i in interventions:
                print(f"  - {i['id'][:8]}... | {i['intervention_type']} | {i['title']}")
            return interventions
        return []


async def main():
    print("="*60)
    print("REAL E2E TEST - Job Application Automation")
    print("="*60)

    # Show available jobs
    print("\nAvailable test jobs:")
    for i, job in enumerate(TEST_JOBS, 1):
        print(f"  {i}. {job['name']}: {job['url']}")

    # Use first job (Greenhouse)
    job_url = TEST_JOBS[0]["url"]

    # Check if custom URL provided
    if len(sys.argv) > 1:
        job_url = sys.argv[1]
        print(f"\nUsing custom URL: {job_url}")

    # Run the test
    result = await test_v2_start(job_url, agent="gemini")

    if result:
        print("\n" + "="*60)
        print("POST-TEST STATUS")
        print("="*60)
        await list_sessions()
        await list_interventions()

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
