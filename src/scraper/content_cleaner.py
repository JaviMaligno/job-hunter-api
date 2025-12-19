"""Content cleaning utilities for AI extraction.

Cleans HTML content to improve LLM extraction quality by:
- Extracting JSON-LD structured data (highest priority)
- Extracting meta tags (og:title, og:description)
- Removing scripts, styles, and other noise
- Extracting main content areas
- Converting to clean markdown/text
"""

import json
import re

import html2text
from bs4 import BeautifulSoup, Comment


def clean_html_for_extraction(html_content: str, max_length: int = 30000) -> str:
    """
    Clean HTML content for better AI extraction.

    Args:
        html_content: Raw HTML content
        max_length: Maximum output length (chars)

    Returns:
        Cleaned text content optimized for LLM extraction
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Extract structured data BEFORE removing scripts
    structured_data = _extract_structured_data(soup)

    # 2. Extract meta tags
    meta_data = _extract_meta_tags(soup)

    # 3. Remove noise elements
    _remove_noise_elements(soup)

    # 4. Try to find main content area
    main_content = _extract_main_content(soup)

    # 5. Convert to clean text/markdown
    cleaned_text = _html_to_text(str(main_content))

    # 6. Post-process text
    cleaned_text = _postprocess_text(cleaned_text)

    # 7. Prepend structured data and meta info for AI context
    prefix_parts = []
    if structured_data:
        prefix_parts.append(f"=== STRUCTURED DATA (JSON-LD) ===\n{structured_data}")
    if meta_data:
        prefix_parts.append(f"=== PAGE METADATA ===\n{meta_data}")

    if prefix_parts:
        prefix = "\n\n".join(prefix_parts) + "\n\n=== PAGE CONTENT ===\n"
        cleaned_text = prefix + cleaned_text

    # 8. Truncate if needed
    if len(cleaned_text) > max_length:
        cleaned_text = cleaned_text[:max_length]

    return cleaned_text


def _extract_structured_data(soup: BeautifulSoup) -> str | None:
    """Extract JSON-LD structured data from script tags."""
    json_ld_scripts = soup.find_all("script", {"type": "application/ld+json"})

    structured_parts = []
    for script in json_ld_scripts:
        try:
            content = script.string
            if content:
                # Parse and re-format for cleaner output
                data = json.loads(content)
                # Check if it's job-related
                if isinstance(data, dict) and data.get("@type") == "JobPosting":
                    # Format key job fields
                    job_info = []
                    if data.get("title"):
                        job_info.append(f"Job Title: {data['title']}")
                    if data.get("hiringOrganization", {}).get("name"):
                        job_info.append(f"Company: {data['hiringOrganization']['name']}")
                    if data.get("jobLocation"):
                        loc = data["jobLocation"]
                        if isinstance(loc, dict):
                            addr = loc.get("address", {})
                            location_parts = [
                                addr.get("addressLocality"),
                                addr.get("addressRegion"),
                                addr.get("addressCountry"),
                            ]
                            location = ", ".join(p for p in location_parts if p)
                            if location:
                                job_info.append(f"Location: {location}")
                    if data.get("employmentType"):
                        job_info.append(f"Employment Type: {data['employmentType']}")
                    if data.get("description"):
                        # Truncate long descriptions
                        desc = data["description"][:2000]
                        job_info.append(f"Description: {desc}")
                    if job_info:
                        structured_parts.append("\n".join(job_info))
        except (json.JSONDecodeError, TypeError):
            continue

    return "\n\n".join(structured_parts) if structured_parts else None


def _extract_meta_tags(soup: BeautifulSoup) -> str | None:
    """Extract relevant meta tags (og:title, og:description, etc)."""
    meta_info = []

    # OpenGraph tags
    og_mappings = {
        "og:title": "Title",
        "og:description": "Description",
        "og:site_name": "Site Name",
    }

    for og_prop, label in og_mappings.items():
        meta = soup.find("meta", property=og_prop)
        if meta and meta.get("content"):
            meta_info.append(f"{label}: {meta['content']}")

    # Twitter tags as fallback
    if not meta_info:
        twitter_mappings = {
            "twitter:title": "Title",
            "twitter:description": "Description",
        }
        for tw_name, label in twitter_mappings.items():
            meta = soup.find("meta", attrs={"name": tw_name})
            if meta and meta.get("content"):
                meta_info.append(f"{label}: {meta['content']}")

    return "\n".join(meta_info) if meta_info else None


def _remove_noise_elements(soup: BeautifulSoup) -> None:
    """Remove script, style, and other noise elements in place."""
    # Tags to remove completely
    noise_tags = [
        "script",
        "style",
        "noscript",
        "iframe",
        "svg",
        "canvas",
        "video",
        "audio",
        "picture",
        "source",
        "template",
        "slot",
    ]

    for tag in noise_tags:
        for element in soup.find_all(tag):
            element.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Remove elements with hidden attributes
    for element in soup.find_all(attrs={"hidden": True}):
        element.decompose()

    for element in soup.find_all(attrs={"aria-hidden": "true"}):
        element.decompose()

    # Remove common navigation/footer elements (but keep if they contain job info)
    for selector in ["nav", "footer"]:
        for element in soup.find_all(selector):
            # Only remove if it doesn't contain job-related keywords
            text = element.get_text(strip=True).lower()
            if not any(
                kw in text
                for kw in [
                    "apply",
                    "requirements",
                    "responsibilities",
                    "salary",
                    "location",
                    "job type",
                ]
            ):
                element.decompose()


def _extract_main_content(soup: BeautifulSoup) -> BeautifulSoup:
    """Extract the main content area from the page."""
    # Priority order for content containers
    content_selectors = [
        # Job-specific containers
        'div[class*="job-description"]',
        'div[class*="job-content"]',
        'div[class*="job-details"]',
        'div[class*="posting-description"]',
        'div[id*="job-description"]',
        'div[id*="job-content"]',
        # Generic content containers
        "main",
        "article",
        'div[role="main"]',
        'div[class*="content"]',
        'div[class*="main"]',
    ]

    for selector in content_selectors:
        content = soup.select_one(selector)
        if content:
            # Check if it has substantial text
            text = content.get_text(strip=True)
            if len(text) > 200:  # Has meaningful content
                return content

    # Fallback to body or full soup
    body = soup.find("body")
    return body if body else soup


def _html_to_text(html: str) -> str:
    """Convert HTML to clean markdown-like text."""
    h = html2text.HTML2Text()
    h.ignore_links = False  # Keep links for context
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0  # No line wrapping
    h.unicode_snob = True
    h.skip_internal_links = True
    h.inline_links = False  # Put links at end
    h.protect_links = True

    return h.handle(html)


def _postprocess_text(text: str) -> str:
    """Post-process the extracted text."""
    # Remove excessive blank lines (more than 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove lines that are just symbols/punctuation
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that are just symbols
        if stripped and not re.match(r"^[\*\-_=#\|]+$", stripped):
            cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)

    return text.strip()
