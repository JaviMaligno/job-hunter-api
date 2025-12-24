#!/usr/bin/env python3
"""
Test the GeminiOrchestratorAgent with a real job application.

Usage:
    poetry run python scripts/test_orchestrator.py
"""

import asyncio
import sys

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from src.agents.gemini_orchestrator import (
    GeminiOrchestratorAgent,
    OrchestratorInput,
    UserFormData,
)


# Test data
TEST_USER = UserFormData(
    first_name="John",
    last_name="Doe",
    email="john.doe@example.com",
    phone="+44 7700 900123",
    linkedin_url="https://linkedin.com/in/johndoe",
    github_url="https://github.com/johndoe",
)

TEST_CV = """
JOHN DOE
Software Engineer | john.doe@example.com | +44 7700 900123

SUMMARY
Experienced full-stack developer with 5+ years building web applications.

SKILLS
- Python, JavaScript, TypeScript
- React, Node.js, FastAPI
- PostgreSQL, MongoDB
- AWS, Docker, Kubernetes

EXPERIENCE
Senior Software Engineer | TechCorp | 2020-Present
- Led development of customer-facing web platform
- Implemented CI/CD pipelines reducing deployment time by 60%

Software Developer | StartupXYZ | 2018-2020
- Built REST APIs serving 1M+ daily requests
- Developed React frontend for internal tools

EDUCATION
BSc Computer Science | University of London | 2018
"""

# Test job URLs
TEST_JOBS = [
    # Breezy - known to work from POC
    "https://soulchi.breezy.hr/p/d6f51a0ba0a8-full-stack-developer",
    # Workable
    # "https://apply.workable.com/metova/j/27E1EE6C09/",
]


async def test_orchestrator():
    """Test the orchestrator with a real job."""
    print("=" * 60)
    print("GeminiOrchestratorAgent Test")
    print("=" * 60)

    agent = GeminiOrchestratorAgent()
    print(f"\n[OK] Agent initialized")
    print(f"     Model: {agent.model}")

    for job_url in TEST_JOBS:
        print(f"\n{'='*60}")
        print(f"Testing: {job_url}")
        print("=" * 60)

        input_data = OrchestratorInput(
            job_url=job_url,
            user_data=TEST_USER,
            cv_content=TEST_CV,
        )

        try:
            result = await agent.run(input_data)

            print(f"\n[RESULT]")
            print(f"  Success: {result.success}")
            print(f"  Status: {result.status}")
            print(f"  Steps: {', '.join(result.steps_completed)}")

            if result.fields_filled:
                print(f"  Fields filled ({len(result.fields_filled)}):")
                for f in result.fields_filled:
                    status = "[OK]" if f.success else "[FAIL]"
                    print(f"    {status} {f.field_name}: {f.value}")

            if result.blocker:
                print(f"  Blocker: {result.blocker.blocker_type}")
                print(f"    {result.blocker.description}")

            if result.error_message:
                print(f"  Error: {result.error_message}")

            if result.final_url:
                print(f"  Final URL: {result.final_url}")

        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_orchestrator())
