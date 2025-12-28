#!/usr/bin/env python3
"""
Run the Job Application Automation Pipeline.

Usage:
    # Apply to all eligible jobs (max 5)
    poetry run python scripts/run_application_pipeline.py --user-id <user_id>

    # Apply to specific jobs
    poetry run python scripts/run_application_pipeline.py --user-id <user_id> --job-ids job1,job2

    # Customize settings
    poetry run python scripts/run_application_pipeline.py --user-id <user_id> --max 10 --delay 60
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()


async def main():
    parser = argparse.ArgumentParser(description="Run the Job Application Automation Pipeline")
    parser.add_argument("--user-id", "-u", required=True, help="User ID to process jobs for")
    parser.add_argument(
        "--max", "-m", type=int, default=5, help="Maximum applications per run (default: 5)"
    )
    parser.add_argument(
        "--delay", "-d", type=int, default=30, help="Seconds between applications (default: 30)"
    )
    parser.add_argument(
        "--job-ids", "-j", help="Comma-separated job IDs to process (default: all eligible)"
    )
    parser.add_argument(
        "--auto-submit",
        action="store_true",
        help="Auto-submit without pausing for review (use with caution!)",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--scan-email", action="store_true", help="Scan email for new jobs before applying"
    )

    args = parser.parse_args()

    # Import after path setup
    import httpx

    from src.automation.application_pipeline import ApplicationPipeline

    print("=" * 60)
    print("JOB APPLICATION AUTOMATION PIPELINE")
    print("=" * 60)
    print(f"User ID: {args.user_id}")
    print(f"Max applications: {args.max}")
    print(f"Delay between apps: {args.delay}s")
    print(f"Auto-submit: {args.auto_submit}")
    print("=" * 60)

    # Optionally scan email first
    if args.scan_email:
        print("\nScanning email for new jobs...")
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{args.api_url}/api/gmail/scan/{args.user_id}",
                params={"save_jobs": True},
                json={"max_emails": 30},
            )
            if response.status_code == 200:
                result = response.json()
                print(f"Scanned {result['emails_scanned']} emails")
                print(f"Extracted {result['jobs_extracted']} new jobs")
                print(f"Skipped {result['jobs_skipped_duplicates']} duplicates")
            else:
                print(f"Warning: Email scan failed: {response.status_code}")

    # Parse job IDs if provided
    job_ids = None
    if args.job_ids:
        job_ids = [j.strip() for j in args.job_ids.split(",")]
        print(f"\nProcessing specific jobs: {len(job_ids)} jobs")

    # Create and run pipeline
    pipeline = ApplicationPipeline(
        api_url=args.api_url,
        user_id=args.user_id,
        max_applications=args.max,
        delay_between_apps=args.delay,
        auto_submit=args.auto_submit,
    )

    report = await pipeline.run(job_ids=job_ids)
    report_path = pipeline.save_report()

    print(f"\nReport saved to: {report_path}")
    print("\nDone!")

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
