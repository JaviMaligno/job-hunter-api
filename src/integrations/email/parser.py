"""Email parser for extracting job information from job alert emails."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse


@dataclass
class ExtractedJob:
    """Extracted job information from email."""

    title: str
    company: str
    location: str | None = None
    job_url: str | None = None
    source_platform: str | None = None


class JobLinkExtractor(HTMLParser):
    """HTML parser to extract job-related links and their context."""

    # Domains that contain job postings
    JOB_DOMAINS = [
        # Major international platforms
        "linkedin.com/jobs",
        "linkedin.com/comm/jobs",
        "indeed.com/viewjob",
        "indeed.com/rc/clk",
        "glassdoor.com/job-listing",
        "glassdoor.com/partner/jobListing",
        "monster.com/job",
        "careerbuilder.com/job",
        "ziprecruiter.com/jobs",
        "ziprecruiter.com/c/",
        "dice.com/job",
        # ATS platforms
        "greenhouse.io/",
        "lever.co/",
        "workable.com/",
        "jobs.lever.co",
        "boards.greenhouse.io",
        "apply.workable.com",
        "smartrecruiters.com",
        "myworkdayjobs.com",
        "breezy.hr/",
        "jobvite.com/",
        "icims.com/",
        "bamboohr.com/jobs",
        "recruitee.com/",
        "ashbyhq.com/",
        # Tech/Startup platforms
        "wellfound.com/jobs",  # formerly AngelList
        "angel.co/jobs",
        "stackoverflow.com/jobs",
        "weworkremotely.com/jobs",
        "remoteok.io/",
        "remote.co/job",
        "flexjobs.com/",
        "getmanfred.com/",  # Spain tech
        # Spanish-speaking platforms
        "infojobs.net/ofertas",
        "infojobs.net/offer",
        "computrabajo.com/",
        "bumeran.com/",
        "trabajando.com/",
        "occ.com.mx/",
        "empleosit.com/",
        "tecnoempleo.com/",
        "getontop.com/",
        # General patterns (less specific, checked last)
        "careers.",
        "job.",
        "trabajar.",
        "empleo.",
        "/careers/",
        "/jobs/",
        "/empleo/",
        "/trabajo/",
        "/vacantes/",
    ]

    # Domains to skip (tracking, unsubscribe, etc.)
    SKIP_PATTERNS = [
        "unsubscribe",
        "optout",
        "preferences",
        "settings",
        "privacy",
        "terms",
        "help",
        "support",
        "facebook.com",
        "twitter.com",
        "instagram.com",
        "youtube.com",
        # Image and media URLs
        "media.licdn.com",
        "/image/",
        "/photo/",
        "/avatar/",
        "/profile-displayphoto",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
    ]

    def __init__(self):
        super().__init__()
        self.job_links: list[dict] = []
        self.current_link: str | None = None
        self.current_text: list[str] = []
        self.in_link = False
        self.link_depth = 0  # Track nested tags inside links
        self.context_before: list[str] = []
        self.context_after: list[str] = []  # Track text after link
        self.all_text: list[str] = []
        self.pending_link: dict | None = None  # Store link waiting for context

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href", "")
            if href and self._is_job_link(href):
                # Finalize any pending link before starting new one
                self._finalize_pending_link()
                self.in_link = True
                self.link_depth = 1
                self.current_link = self._clean_url(href)
                self.current_text = []
                self.context_before = self.all_text[-15:] if self.all_text else []
        elif self.in_link:
            self.link_depth += 1

    def handle_endtag(self, tag):
        if self.in_link:
            self.link_depth -= 1
            if tag == "a" or self.link_depth <= 0:
                if self.current_link:
                    # Store link with text and context, wait for more context
                    self.pending_link = {
                        "url": self.current_link,
                        "text": " ".join(self.current_text).strip(),
                        "context_before": self.context_before.copy(),
                        "context_after": [],
                    }
                self.in_link = False
                self.current_link = None
                self.current_text = []
                self.link_depth = 0

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.all_text.append(text)
            if self.in_link:
                self.current_text.append(text)
            elif self.pending_link:
                # Collect context after the link
                self.pending_link["context_after"].append(text)
                # After collecting some context, finalize the link
                if len(self.pending_link["context_after"]) >= 5:
                    self._finalize_pending_link()

    def _finalize_pending_link(self):
        """Add pending link to job_links list."""
        if self.pending_link:
            combined_context = (
                " ".join(self.pending_link["context_before"])
                + " "
                + " ".join(self.pending_link["context_after"])
            ).strip()
            self.job_links.append(
                {
                    "url": self.pending_link["url"],
                    "text": self.pending_link["text"],
                    "context": combined_context,
                }
            )
            self.pending_link = None

    def close(self):
        """Finalize any pending link when parsing is done."""
        self._finalize_pending_link()
        super().close()

    def _is_job_link(self, url: str) -> bool:
        """Check if URL is likely a job posting link."""
        url_lower = url.lower()

        # Skip tracking/utility links
        for skip in self.SKIP_PATTERNS:
            if skip in url_lower:
                return False

        # Check for job-related domains
        for domain in self.JOB_DOMAINS:
            if domain in url_lower:
                return True

        # Check for common job URL patterns
        if any(
            pattern in url_lower
            for pattern in [
                "/job/",
                "/jobs/",
                "/vacancy/",
                "/opening/",
                "/position/",
                "/empleo/",
                "/oferta/",
            ]
        ):
            return True

        return False

    def _clean_url(self, url: str) -> str:
        """Clean tracking URLs and extract the actual job URL."""
        # Handle LinkedIn tracking redirects
        if "linkedin.com" in url and "/comm/" in url:
            # Extract actual URL from LinkedIn tracking
            try:
                parsed = urlparse(url)
                if "trk" in url:
                    # Try to extract the real URL
                    return url.split("?")[0]
            except Exception:
                pass

        # Handle Indeed redirects
        if "indeed.com/rc/clk" in url:
            try:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if "jk" in params:
                    job_key = params["jk"][0]
                    return f"https://indeed.com/viewjob?jk={job_key}"
            except Exception:
                pass

        # Handle Google redirects
        if "google.com/url" in url:
            try:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if "url" in params:
                    return unquote(params["url"][0])
                if "q" in params:
                    return unquote(params["q"][0])
            except Exception:
                pass

        return url


def detect_platform(url: str, sender: str = "") -> str:
    """Detect the job platform from URL or sender."""
    url_lower = url.lower()
    sender_lower = sender.lower()

    # Major international platforms
    if "linkedin.com" in url_lower or "linkedin" in sender_lower:
        return "linkedin"
    if "indeed.com" in url_lower or "indeed" in sender_lower:
        return "indeed"
    if "glassdoor.com" in url_lower or "glassdoor" in sender_lower:
        return "glassdoor"
    if "monster.com" in url_lower or "monster" in sender_lower:
        return "monster"
    if "careerbuilder.com" in url_lower or "careerbuilder" in sender_lower:
        return "careerbuilder"
    if "ziprecruiter.com" in url_lower or "ziprecruiter" in sender_lower:
        return "ziprecruiter"
    if "dice.com" in url_lower or "dice" in sender_lower:
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
    if "stackoverflow.com/jobs" in url_lower:
        return "stackoverflow"
    if "weworkremotely.com" in url_lower:
        return "weworkremotely"
    if "remoteok.io" in url_lower:
        return "remoteok"
    if "remote.co" in url_lower:
        return "remoteco"
    if "flexjobs.com" in url_lower:
        return "flexjobs"
    if "getmanfred.com" in url_lower or "manfred" in sender_lower:
        return "manfred"

    # Spanish-speaking platforms
    if "infojobs.net" in url_lower or "infojobs" in sender_lower:
        return "infojobs"
    if "computrabajo.com" in url_lower or "computrabajo" in sender_lower:
        return "computrabajo"
    if "bumeran.com" in url_lower or "bumeran" in sender_lower:
        return "bumeran"
    if "trabajando.com" in url_lower:
        return "trabajando"
    if "occ.com.mx" in url_lower:
        return "occ"
    if "empleosit.com" in url_lower:
        return "empleosit"
    if "tecnoempleo.com" in url_lower or "tecnoempleo" in sender_lower:
        return "tecnoempleo"
    if "getontop.com" in url_lower:
        return "getontop"

    # Special senders
    if "jackandjillemployment" in sender_lower or "jack&jill" in sender_lower:
        return "jack_and_jill"

    return "other"


def extract_job_info_from_text(
    link_text: str, context: str, url: str
) -> tuple[str, str, str | None]:
    """
    Extract job title, company, and location from link text and context.

    Returns (title, company, location)
    """
    # Clean the link text first
    clean_text = link_text.strip()

    # Remove common prefixes
    clean_text = re.sub(r"^jobs?\s+similar\s+to\s+", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"^new\s+job[s]?:?\s*", "", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"^you may be a fit for\s+", "", clean_text, flags=re.IGNORECASE)

    # Try to extract from link text first (more reliable)
    # Pattern: "Title at Company - Location" or "Title at Company, Location"
    match = re.search(
        r"^([^@]+?)\s+at\s+([^,–-]+?)(?:\s*[,–-]\s*([^,–-]+))?$", clean_text, re.IGNORECASE
    )
    if match:
        title = match.group(1).strip()
        company = match.group(2).strip()
        location = match.group(3).strip() if match.group(3) else None
        # Limit length to avoid garbage
        if len(title) > 3 and len(title) < 80 and len(company) > 1 and len(company) < 60:
            return title, company, location

    # Pattern: "Title | Company"
    match = re.search(r"^([^|]+)\s*\|\s*([^|]+)$", clean_text, re.IGNORECASE)
    if match and len(match.group(1)) < 80 and len(match.group(2)) < 60:
        return match.group(1).strip(), match.group(2).strip(), None

    # Pattern: "Title - Company" (only if exactly 2 parts)
    if " - " in clean_text:
        parts = clean_text.split(" - ")
        if len(parts) == 2 and 3 < len(parts[0]) < 80 and 1 < len(parts[1]) < 60:
            return parts[0].strip(), parts[1].strip(), None

    # Look for job title keywords
    title_keywords = [
        r"((?:senior|junior|lead|staff|principal|freelance)?\s*(?:software|data|ml|ai|machine learning|full[- ]?stack|front[- ]?end|back[- ]?end|devops|cloud|platform|python)?\s*(?:engineer|scientist|developer|architect|analyst|researcher|specialist))",
        r"((?:product|project|program|engineering|technical)?\s*manager)",
        r"((?:ux|ui|product|graphic)?\s*designer)",
    ]

    for pattern in title_keywords:
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            title = match.group(1).strip()
            if title:
                # Try to find company after "at"
                company_match = re.search(
                    r"\bat\s+([A-Z][A-Za-z0-9\s&]+?)(?:\s*[,–-]|$)", clean_text
                )
                company = (
                    company_match.group(1).strip()[:50] if company_match else "Unknown Company"
                )
                return title.title(), company, None

    # Use link text as title if reasonable length
    if clean_text and 5 < len(clean_text) < 100:
        # Look for company in context
        company = "Unknown Company"
        company_match = re.search(r"\bat\s+([A-Z][A-Za-z0-9\s&]+?)(?:\s*[,–-]|\s+|$)", context)
        if company_match:
            company = company_match.group(1).strip()[:50]
        return clean_text[:80], company, None

    # Fallback: try to extract from context
    if context:
        context_clean = re.sub(r"^jobs?\s+similar\s+to\s+", "", context, flags=re.IGNORECASE)
        match = re.search(r"^([^@]+?)\s+at\s+([^,–-\s]+)", context_clean, re.IGNORECASE)
        if match and len(match.group(1)) < 60:
            return match.group(1).strip(), match.group(2).strip()[:50], None

    return "Job Opening", "Unknown Company", None


def parse_job_email(body: str, sender: str = "", subject: str = "") -> list[ExtractedJob]:
    """
    Parse an email body and extract job information.

    Args:
        body: HTML or plain text email body
        sender: Email sender address
        subject: Email subject

    Returns:
        List of ExtractedJob objects
    """
    jobs = []
    seen_urls = set()

    # Parse HTML to extract job links
    parser = JobLinkExtractor()
    try:
        parser.feed(body)
        parser.close()  # Finalize any pending links
    except Exception:
        # If HTML parsing fails, try to extract URLs with regex
        pass

    # First pass: collect best link data for each unique URL
    url_data: dict[str, dict] = {}
    for link in parser.job_links:
        url = link["url"]

        # Skip non-job links (search pages, collections, etc.)
        if any(
            skip in url.lower() for skip in ["collections/", "search", "alerts", "notifications"]
        ):
            continue

        # Normalize URL for deduplication (remove tracking params)
        normalized_url = url.split("?")[0].rstrip("/")

        # If we haven't seen this URL, or this link has better text, use it
        current = url_data.get(normalized_url)
        link_text = link["text"].strip()
        if current is None:
            url_data[normalized_url] = link
        elif not current["text"].strip() and link_text:
            # Prefer link with actual text
            url_data[normalized_url] = link
        elif len(link_text) > len(current["text"].strip()):
            # Prefer longer text
            url_data[normalized_url] = link

    # Second pass: extract job info from best links
    for normalized_url, link in url_data.items():
        url = link["url"]

        # Skip if we've already processed this URL
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)

        # Extract job info
        title, company, location = extract_job_info_from_text(link["text"], link["context"], url)

        # Detect platform
        platform = detect_platform(url, sender)

        jobs.append(
            ExtractedJob(
                title=title,
                company=company,
                location=location,
                job_url=url,
                source_platform=platform,
            )
        )

    # If no links found via HTML parsing, try regex extraction
    if not jobs:
        # Extract URLs with regex
        url_pattern = r'https?://[^\s<>"\']+(?:job|career|position|vacancy|empleo)[^\s<>"\']*'
        urls = re.findall(url_pattern, body, re.IGNORECASE)

        for url in urls[:10]:  # Limit to first 10
            if url in seen_urls:
                continue
            seen_urls.add(url)

            platform = detect_platform(url, sender)

            # Try to extract title from subject if available
            title = subject if subject else "Job Opening"

            jobs.append(
                ExtractedJob(
                    title=title,
                    company="Unknown Company",
                    location=None,
                    job_url=url,
                    source_platform=platform,
                )
            )

    return jobs
