"""Job URL scraper for extracting job details from various platforms."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx


@dataclass
class ScrapedJob:
    """Scraped job information from a URL."""

    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    job_type: str | None = None  # Full-time, Part-time, Contract, etc.
    salary: str | None = None
    platform: str = "unknown"
    success: bool = False
    error: str | None = None


class HTMLTextExtractor(HTMLParser):
    """Extract text content from HTML."""

    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self.skip_tags = {"script", "style", "meta", "link", "noscript"}
        self.current_skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.skip_tags:
            self.current_skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags and self.current_skip > 0:
            self.current_skip -= 1

    def handle_data(self, data):
        if self.current_skip == 0:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    def get_text(self) -> str:
        return " ".join(self.text_parts)


def _detect_platform(url: str) -> str:
    """Detect job platform from URL."""
    url_lower = url.lower()

    # Major international platforms
    if "linkedin.com" in url_lower:
        return "linkedin"
    if "indeed.com" in url_lower:
        return "indeed"
    if "glassdoor.com" in url_lower:
        return "glassdoor"
    if "monster.com" in url_lower:
        return "monster"
    if "careerbuilder.com" in url_lower:
        return "careerbuilder"
    if "ziprecruiter.com" in url_lower:
        return "ziprecruiter"
    if "dice.com" in url_lower:
        return "dice"

    # ATS platforms
    if "greenhouse.io" in url_lower or "boards.greenhouse" in url_lower:
        return "greenhouse"
    if "lever.co" in url_lower or "jobs.lever" in url_lower:
        return "lever"
    if "workable.com" in url_lower:
        return "workable"
    if "smartrecruiters.com" in url_lower:
        return "smartrecruiters"
    if "myworkdayjobs.com" in url_lower:
        return "workday"
    if "breezy.hr" in url_lower:
        return "breezy"
    if "jobvite.com" in url_lower:
        return "jobvite"
    if "icims.com" in url_lower:
        return "icims"
    if "bamboohr.com" in url_lower:
        return "bamboohr"
    if "recruitee.com" in url_lower:
        return "recruitee"
    if "ashbyhq.com" in url_lower:
        return "ashby"

    # Tech/Startup platforms
    if "wellfound.com" in url_lower or "angel.co" in url_lower:
        return "wellfound"
    if "weworkremotely.com" in url_lower:
        return "weworkremotely"
    if "remoteok.io" in url_lower:
        return "remoteok"
    if "getmanfred.com" in url_lower:
        return "manfred"

    # Spanish-speaking platforms
    if "infojobs.net" in url_lower:
        return "infojobs"
    if "computrabajo.com" in url_lower:
        return "computrabajo"
    if "bumeran.com" in url_lower:
        return "bumeran"
    if "tecnoempleo.com" in url_lower:
        return "tecnoempleo"

    return "other"


def _extract_meta_content(html: str, name: str) -> str | None:
    """Extract content from meta tags."""
    # Try og: prefix first, then regular name
    patterns = [
        rf'<meta\s+property=["\']og:{name}["\']\s+content=["\']([^"\']+)["\']',
        rf'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']og:{name}["\']',
        rf'<meta\s+name=["\']twitter:{name}["\']\s+content=["\']([^"\']+)["\']',
        rf'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']' if name == "description" else None,
    ]

    for pattern in patterns:
        if pattern:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1).strip()

    return None


def _extract_title(html: str) -> str | None:
    """Extract page title."""
    # Try meta title first
    og_title = _extract_meta_content(html, "title")
    if og_title:
        return og_title

    # Try regular title tag
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    return None


def _extract_linkedin_job(html: str) -> ScrapedJob:
    """Extract job details from LinkedIn job page."""
    job = ScrapedJob(platform="linkedin", success=True)

    # Title from og:title or page title
    title = _extract_meta_content(html, "title")
    if title:
        # LinkedIn format: "Job Title at Company | LinkedIn"
        parts = title.split(" at ")
        if len(parts) >= 2:
            job.title = parts[0].strip()
            company_part = parts[1].split(" | ")[0].strip()
            job.company = company_part
        else:
            job.title = title.split(" | ")[0].strip()

    # Description
    job.description = _extract_meta_content(html, "description")

    # Try to extract location from various patterns
    location_patterns = [
        r'"companyLocation":\s*"([^"]+)"',
        r'"jobLocation"[^}]*"addressLocality":\s*"([^"]+)"',
        r'class="[^"]*job-location[^"]*"[^>]*>([^<]+)',
    ]
    for pattern in location_patterns:
        match = re.search(pattern, html)
        if match:
            job.location = match.group(1).strip()
            break

    return job


def _extract_indeed_job(html: str) -> ScrapedJob:
    """Extract job details from Indeed job page."""
    job = ScrapedJob(platform="indeed", success=True)

    # Title
    title_match = re.search(r'class="[^"]*jobsearch-JobInfoHeader-title[^"]*"[^>]*>([^<]+)', html)
    if title_match:
        job.title = title_match.group(1).strip()
    else:
        job.title = _extract_title(html)

    # Company
    company_match = re.search(r'data-company-name="true"[^>]*>([^<]+)', html)
    if company_match:
        job.company = company_match.group(1).strip()

    # Description
    job.description = _extract_meta_content(html, "description")

    # Location
    location_match = re.search(r'data-testid="job-location"[^>]*>([^<]+)', html)
    if location_match:
        job.location = location_match.group(1).strip()

    return job


def _extract_greenhouse_job(html: str) -> ScrapedJob:
    """Extract job details from Greenhouse job page."""
    job = ScrapedJob(platform="greenhouse", success=True)

    # Title
    title_match = re.search(r'class="[^"]*app-title[^"]*"[^>]*>([^<]+)', html)
    if title_match:
        job.title = title_match.group(1).strip()
    else:
        job.title = _extract_title(html)

    # Company from og:site_name or URL
    company = _extract_meta_content(html, "site_name")
    if company:
        job.company = company

    # Description
    job.description = _extract_meta_content(html, "description")

    # Location
    location_match = re.search(r'class="[^"]*location[^"]*"[^>]*>([^<]+)', html)
    if location_match:
        job.location = location_match.group(1).strip()

    return job


def _extract_lever_job(html: str) -> ScrapedJob:
    """Extract job details from Lever job page."""
    job = ScrapedJob(platform="lever", success=True)

    # Title
    title_match = re.search(r'<h2>([^<]+)</h2>', html)
    if title_match:
        job.title = title_match.group(1).strip()
    else:
        job.title = _extract_title(html)

    # Company from og:site_name
    job.company = _extract_meta_content(html, "site_name")

    # Description
    job.description = _extract_meta_content(html, "description")

    # Location
    location_match = re.search(r'class="[^"]*location[^"]*"[^>]*>([^<]+)', html)
    if location_match:
        job.location = location_match.group(1).strip()

    return job


def _extract_infojobs_job(html: str) -> ScrapedJob:
    """Extract job details from InfoJobs job page."""
    job = ScrapedJob(platform="infojobs", success=True)

    # Title from og:title or structured data
    job.title = _extract_meta_content(html, "title")
    if job.title and " - " in job.title:
        # Format is usually "Title - Company - InfoJobs"
        parts = job.title.split(" - ")
        if len(parts) >= 2:
            job.title = parts[0].strip()
            job.company = parts[1].strip() if "InfoJobs" not in parts[1] else None

    # Company from structured data
    if not job.company:
        company_match = re.search(r'"hiringOrganization"[^}]*"name":\s*"([^"]+)"', html)
        if company_match:
            job.company = company_match.group(1).strip()

    # Description
    job.description = _extract_meta_content(html, "description")

    # Location from structured data
    location_match = re.search(r'"jobLocation"[^}]*"addressLocality":\s*"([^"]+)"', html)
    if location_match:
        job.location = location_match.group(1).strip()

    return job


def _extract_computrabajo_job(html: str) -> ScrapedJob:
    """Extract job details from Computrabajo job page."""
    job = ScrapedJob(platform="computrabajo", success=True)

    # Title
    job.title = _extract_meta_content(html, "title")
    if job.title and " en " in job.title:
        # Format: "Title en Company - Computrabajo"
        parts = job.title.split(" en ")
        if len(parts) >= 2:
            job.title = parts[0].strip()
            company_part = parts[1].split(" - ")[0].strip()
            job.company = company_part

    # Description
    job.description = _extract_meta_content(html, "description")

    # Company from structured data if not found
    if not job.company:
        company_match = re.search(r'"hiringOrganization"[^}]*"name":\s*"([^"]+)"', html)
        if company_match:
            job.company = company_match.group(1).strip()

    return job


def _extract_generic_job(html: str) -> ScrapedJob:
    """Generic job extraction using common patterns."""
    job = ScrapedJob(platform="other", success=True)

    # Title
    job.title = _extract_title(html)

    # Description
    job.description = _extract_meta_content(html, "description")

    # Try to find company in common patterns
    company_patterns = [
        r'"hiringOrganization"[^}]*"name":\s*"([^"]+)"',
        r'"companyName":\s*"([^"]+)"',
        r'"employer"[^}]*"name":\s*"([^"]+)"',
        r'class="[^"]*company[^"]*"[^>]*>([^<]+)',
        r'class="[^"]*employer[^"]*"[^>]*>([^<]+)',
    ]
    for pattern in company_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            job.company = match.group(1).strip()
            break

    # Try to find location
    location_patterns = [
        r'"jobLocation"[^}]*"addressLocality":\s*"([^"]+)"',
        r'"addressRegion":\s*"([^"]+)"',
        r'class="[^"]*location[^"]*"[^>]*>([^<]+)',
        r'class="[^"]*ciudad[^"]*"[^>]*>([^<]+)',  # Spanish
    ]
    for pattern in location_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            job.location = match.group(1).strip()
            break

    # Try to find job type
    job_type_patterns = [
        r'"employmentType":\s*"([^"]+)"',
        r'class="[^"]*job-type[^"]*"[^>]*>([^<]+)',
        r'class="[^"]*tipo-contrato[^"]*"[^>]*>([^<]+)',  # Spanish
    ]
    for pattern in job_type_patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            job.job_type = match.group(1).strip()
            break

    return job


async def scrape_job_url(url: str, timeout: float = 30.0) -> ScrapedJob:
    """
    Scrape job details from a URL.

    Args:
        url: The job posting URL
        timeout: Request timeout in seconds

    Returns:
        ScrapedJob with extracted details
    """
    platform = _detect_platform(url)

    try:
        # Fetch the page with browser-like headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            html = response.text

        # Extract based on platform
        if platform == "linkedin":
            job = _extract_linkedin_job(html)
        elif platform == "indeed":
            job = _extract_indeed_job(html)
        elif platform == "greenhouse":
            job = _extract_greenhouse_job(html)
        elif platform == "lever":
            job = _extract_lever_job(html)
        elif platform == "infojobs":
            job = _extract_infojobs_job(html)
        elif platform == "computrabajo":
            job = _extract_computrabajo_job(html)
        else:
            job = _extract_generic_job(html)

        job.platform = platform

        # Clean up any HTML entities in extracted text
        if job.title:
            job.title = re.sub(r'&[a-zA-Z]+;', ' ', job.title).strip()
        if job.company:
            job.company = re.sub(r'&[a-zA-Z]+;', ' ', job.company).strip()
        if job.description:
            job.description = re.sub(r'&[a-zA-Z]+;', ' ', job.description).strip()

        return job

    except httpx.TimeoutException:
        return ScrapedJob(
            platform=platform,
            success=False,
            error="Request timed out. The job page took too long to load.",
        )
    except httpx.HTTPStatusError as e:
        return ScrapedJob(
            platform=platform,
            success=False,
            error=f"HTTP error {e.response.status_code}: Unable to access the job page.",
        )
    except Exception as e:
        return ScrapedJob(
            platform=platform,
            success=False,
            error=f"Error scraping job: {str(e)}",
        )
