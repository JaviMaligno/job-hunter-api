"""Job integrations module."""

from src.integrations.jobs.scraper import ScrapedJob, scrape_job_url

__all__ = ["ScrapedJob", "scrape_job_url"]
