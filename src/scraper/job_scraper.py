"""Job scraper service for extracting job details from URLs.

Hybrid approach:
1. Fast path: Traditional HTTP + BeautifulSoup scraping
2. Slow path: Playwright rendering + AI extraction (for JS-heavy sites)
"""

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ScrapedJob:
    """Scraped job data."""

    title: str
    company: str | None = None
    location: str | None = None
    description: str | None = None
    salary_range: str | None = None
    job_type: str | None = None
    source_platform: str | None = None
    requirements: list[str] | None = None
    extraction_method: str = "traditional"  # "traditional", "playwright", "ai"


# Sites known to require JavaScript rendering
JS_HEAVY_SITES = [
    "bamboohr.com",
    "workday.com",
    "myworkdayjobs.com",
    "phenom.com",
    "pepsicojobs.com",
    "icims.com",
    "smartrecruiters.com",
    "successfactors.com",
]


class JobScraper:
    """Scrapes job postings from various job boards."""

    # Common user agent to avoid blocks
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Platform-specific selectors
    PLATFORM_SELECTORS = {
        "linkedin.com": {
            "title": [
                "h1.top-card-layout__title",
                "h1.topcard__title",
                ".job-details-jobs-unified-top-card__job-title h1",
                "h1",
            ],
            "company": [
                "a.topcard__org-name-link",
                ".topcard__org-name-link",
                ".job-details-jobs-unified-top-card__company-name",
                ".top-card-layout__card a[data-tracking-control-name='public_jobs_topcard-org-name']",
            ],
            "location": [
                ".topcard__flavor--bullet",
                ".job-details-jobs-unified-top-card__bullet",
                "span.topcard__flavor",
            ],
            "description": [
                ".description__text",
                ".show-more-less-html__markup",
                ".jobs-description-content__text",
            ],
        },
        "indeed.com": {
            "title": [
                "h1.jobsearch-JobInfoHeader-title",
                ".jobsearch-JobInfoHeader-title",
                "h1[data-testid='jobsearch-JobInfoHeader-title']",
            ],
            "company": [
                "div[data-testid='inlineHeader-companyName']",
                ".jobsearch-InlineCompanyRating-companyHeader a",
                ".jobsearch-CompanyInfoContainer a",
            ],
            "location": [
                "div[data-testid='inlineHeader-companyLocation']",
                ".jobsearch-JobInfoHeader-subtitle > div:nth-child(2)",
            ],
            "description": [
                "#jobDescriptionText",
                ".jobsearch-jobDescriptionText",
            ],
        },
        "greenhouse.io": {
            "title": ["h1.app-title", "h1"],
            "company": [".company-name", "meta[property='og:site_name']"],
            "location": [".location", ".job-location"],
            "description": ["#content", ".content"],
        },
        "lever.co": {
            "title": [".posting-headline h2", "h2"],
            "company": [".posting-headline .company-name", "meta[property='og:site_name']"],
            "location": [".posting-categories .location", ".location"],
            "description": [".posting-description", ".content"],
        },
        "workday.com": {
            "title": ["h1[data-automation-id='jobPostingHeader']", "h1"],
            "company": [],
            "location": ["[data-automation-id='location']"],
            "description": ["[data-automation-id='jobPostingDescription']"],
        },
    }

    def __init__(self, timeout: float = 30.0, use_ai_fallback: bool = True):
        """Initialize the scraper."""
        self.timeout = timeout
        self.use_ai_fallback = use_ai_fallback

    async def scrape(self, url: str) -> ScrapedJob:
        """
        Scrape job details from a URL using hybrid approach.

        1. Try traditional HTTP scraping first (fast, free)
        2. If extraction incomplete, try HTTP + AI extraction
        3. If AI extraction fails, try Playwright + AI as last resort

        Args:
            url: The job posting URL

        Returns:
            ScrapedJob with extracted data

        Raises:
            httpx.HTTPError: If the request fails
            ValueError: If unable to extract required data
        """
        # Detect platform
        platform = self._detect_platform(url)

        # Check if this is a known JS-heavy site
        is_js_heavy = self._is_js_heavy_site(url)

        # For JS-heavy sites, try Playwright + AI first (gets fully rendered content)
        if is_js_heavy and self.use_ai_fallback:
            logger.info(f"JS-heavy site detected: {url}, trying Playwright + AI extraction")
            try:
                return await self._scrape_with_playwright_ai(url, platform)
            except Exception as e:
                logger.warning(f"Playwright + AI extraction failed for {url}: {e}")
                # Fall back to HTTP + AI (may work if JSON data in static HTML)
                try:
                    logger.info(f"Falling back to HTTP + AI for {url}")
                    return await self._scrape_with_httpx_ai(url, platform)
                except Exception as http_e:
                    logger.error(f"HTTP + AI also failed: {http_e}")
                    raise ValueError(f"Could not extract job data from {url}. Site may require manual import.")

        # Try traditional scraping first
        try:
            result = await self._scrape_traditional(url, platform)

            # Check if extraction was successful (has description)
            if result.description and len(result.description) > 100:
                logger.info(f"Traditional scraping successful for {url}")
                return result

            # Extraction incomplete, try AI fallback with HTTP content
            if self.use_ai_fallback:
                logger.info(f"Traditional scraping incomplete for {url}, trying AI fallback")
                return await self._scrape_with_httpx_ai(url, platform)

            return result

        except (ValueError, httpx.HTTPError) as e:
            logger.warning(f"Traditional scraping failed for {url}: {e}")

            if self.use_ai_fallback:
                logger.info(f"Trying AI fallback for {url}")
                return await self._scrape_with_httpx_ai(url, platform)

            raise

    def _is_js_heavy_site(self, url: str) -> bool:
        """Check if URL belongs to a known JS-heavy site."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        for js_site in JS_HEAVY_SITES:
            if js_site in domain:
                return True

        return False

    async def _scrape_traditional(self, url: str, platform: str | None) -> ScrapedJob:
        """Traditional HTTP + BeautifulSoup scraping."""
        # Fetch page content
        html = await self._fetch_page(url)

        # Parse HTML
        soup = BeautifulSoup(html, "html.parser")

        # Get platform-specific selectors or use generic ones
        selectors = self.PLATFORM_SELECTORS.get(platform, {})

        # Extract job details
        title = self._extract_text(soup, selectors.get("title", []))
        if not title:
            title = self._extract_generic_title(soup)

        if not title:
            raise ValueError(f"Could not extract job title from {url}")

        company = self._extract_text(soup, selectors.get("company", []))
        if not company:
            company = self._extract_generic_company(soup)

        location = self._extract_text(soup, selectors.get("location", []))
        if not location:
            location = self._extract_generic_location(soup)

        description = self._extract_text(soup, selectors.get("description", []))
        if not description:
            description = self._extract_generic_description(soup)

        salary_range = self._extract_salary(soup)
        job_type = self._extract_job_type(soup)

        return ScrapedJob(
            title=title,
            company=company,
            location=location,
            description=description,
            salary_range=salary_range,
            job_type=job_type,
            source_platform=platform,
            extraction_method="traditional",
        )

    async def _scrape_with_httpx_ai(self, url: str, platform: str | None) -> ScrapedJob:
        """Scrape using HTTP fetch + AI extraction (no Playwright).

        This is faster and avoids Playwright issues on Windows.
        May not work well for heavily JS-rendered sites.
        """
        from src.scraper.ai_extractor import get_gemini_extractor

        # Fetch page content with httpx
        html_content = await self._fetch_page(url)

        # Extract with AI
        extractor = get_gemini_extractor()
        ai_result = await extractor.extract(html_content, url)

        return ScrapedJob(
            title=ai_result.title,
            company=ai_result.company,
            location=ai_result.location,
            description=ai_result.description,
            salary_range=ai_result.salary_range,
            job_type=ai_result.job_type,
            source_platform=platform,
            requirements=ai_result.requirements,
            extraction_method=f"ai-httpx:{ai_result.model_used}",
        )

    async def _scrape_with_playwright_ai(self, url: str, platform: str | None) -> ScrapedJob:
        """Scrape using Playwright rendering + AI extraction."""
        from src.scraper.ai_extractor import get_gemini_extractor

        # Render page with Playwright
        html_content = await self._render_with_playwright(url)

        # Extract with AI
        extractor = get_gemini_extractor()
        ai_result = await extractor.extract(html_content, url)

        return ScrapedJob(
            title=ai_result.title,
            company=ai_result.company,
            location=ai_result.location,
            description=ai_result.description,
            salary_range=ai_result.salary_range,
            job_type=ai_result.job_type,
            source_platform=platform,
            requirements=ai_result.requirements,
            extraction_method=f"ai-playwright:{ai_result.model_used}",
        )

    async def _render_with_playwright(self, url: str) -> str:
        """Render page with Playwright to get JS-rendered content.

        Uses sync Playwright in a thread to work around Windows asyncio limitations.
        """
        import asyncio

        # Use sync playwright in a thread to avoid Windows asyncio subprocess issues
        def _render_sync() -> str:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        user_agent=self.USER_AGENT,
                        viewport={"width": 1920, "height": 1080},
                    )
                    page = context.new_page()

                    # Navigate and wait for content to load
                    page.goto(url, wait_until="networkidle", timeout=int(self.timeout * 1000))

                    # Wait a bit more for dynamic content
                    page.wait_for_timeout(2000)

                    # Get the rendered HTML
                    content = page.content()

                    return content
                finally:
                    browser.close()

        # Run sync playwright in thread pool
        return await asyncio.to_thread(_render_sync)

    def _detect_platform(self, url: str) -> str | None:
        """Detect the job board platform from the URL."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        for platform in self.PLATFORM_SELECTORS:
            if platform in domain:
                return platform

        return None

    async def _fetch_page(self, url: str) -> str:
        """Fetch the page content."""
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={"User-Agent": self.USER_AGENT},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

    def _extract_text(self, soup: BeautifulSoup, selectors: list[str]) -> str | None:
        """Extract text using a list of selectors, trying each until one succeeds."""
        for selector in selectors:
            # Handle meta tags specially
            if selector.startswith("meta["):
                element = soup.select_one(selector)
                if element and element.get("content"):
                    return element["content"].strip()
            else:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(separator=" ", strip=True)
                    if text:
                        return text
        return None

    def _extract_generic_title(self, soup: BeautifulSoup) -> str | None:
        """Try to extract job title using generic patterns."""
        # Try h1 tags
        h1 = soup.find("h1")
        if h1:
            text = h1.get_text(strip=True)
            if text and len(text) < 200:  # Reasonable title length
                return text

        # Try og:title meta tag
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()

        # Try page title
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Clean common suffixes
            for suffix in [" | LinkedIn", " - Indeed.com", " | Glassdoor"]:
                title = title.replace(suffix, "")
            return title.strip()

        return None

    def _extract_generic_company(self, soup: BeautifulSoup) -> str | None:
        """Try to extract company name using generic patterns."""
        # Look for common company name patterns
        patterns = [
            {"class_": re.compile(r"company", re.I)},
            {"class_": re.compile(r"employer", re.I)},
            {"class_": re.compile(r"organization", re.I)},
        ]

        for pattern in patterns:
            element = soup.find(["a", "span", "div"], **pattern)
            if element:
                text = element.get_text(strip=True)
                if text and len(text) < 100:
                    return text

        return None

    def _extract_generic_location(self, soup: BeautifulSoup) -> str | None:
        """Try to extract location using generic patterns."""
        patterns = [
            {"class_": re.compile(r"location", re.I)},
            {"class_": re.compile(r"address", re.I)},
        ]

        for pattern in patterns:
            element = soup.find(["span", "div", "p"], **pattern)
            if element:
                text = element.get_text(strip=True)
                if text and len(text) < 150:
                    return text

        return None

    def _extract_generic_description(self, soup: BeautifulSoup) -> str | None:
        """Try to extract job description using generic patterns."""
        patterns = [
            {"class_": re.compile(r"description", re.I)},
            {"class_": re.compile(r"job.?content", re.I)},
            {"id": re.compile(r"description", re.I)},
        ]

        for pattern in patterns:
            element = soup.find(["div", "section", "article"], **pattern)
            if element:
                text = element.get_text(separator="\n", strip=True)
                if text and len(text) > 100:  # Reasonable description length
                    return text[:10000]  # Limit length

        return None

    def _extract_salary(self, soup: BeautifulSoup) -> str | None:
        """Try to extract salary information."""
        # Look for salary patterns in text
        salary_patterns = [
            r"\$[\d,]+\s*[-–]\s*\$[\d,]+",  # $100,000 - $150,000
            r"£[\d,]+\s*[-–]\s*£[\d,]+",  # £50,000 - £70,000
            r"€[\d,]+\s*[-–]\s*€[\d,]+",  # €50,000 - €70,000
            r"\$[\d,]+\s*(?:k|K)\s*[-–]\s*\$?[\d,]+\s*(?:k|K)?",  # $100k - $150k
        ]

        # Search in elements with salary-related classes
        salary_elements = soup.find_all(
            ["span", "div", "p"],
            class_=re.compile(r"salary|compensation|pay", re.I),
        )

        for element in salary_elements:
            text = element.get_text(strip=True)
            for pattern in salary_patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group()

        # Search in full page text as fallback
        page_text = soup.get_text()
        for pattern in salary_patterns:
            match = re.search(pattern, page_text)
            if match:
                return match.group()

        return None

    def _extract_job_type(self, soup: BeautifulSoup) -> str | None:
        """Try to extract job type (full-time, part-time, etc.)."""
        job_types = [
            "full-time",
            "full time",
            "part-time",
            "part time",
            "contract",
            "temporary",
            "internship",
            "freelance",
            "remote",
        ]

        # Search in elements with job type related classes
        type_elements = soup.find_all(
            ["span", "div", "li"],
            class_=re.compile(r"type|employment|work.?arrangement", re.I),
        )

        for element in type_elements:
            text = element.get_text(strip=True).lower()
            for job_type in job_types:
                if job_type in text:
                    return job_type.title().replace(" ", "-")

        return None
