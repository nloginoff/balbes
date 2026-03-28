"""
Fetch URL skill — curl-analogue for reading web page content.

Downloads a URL, strips HTML to readable text (Markdown-style),
and returns the first MAX_CONTENT_CHARS characters.
"""

import logging
import re

import httpx

from shared.config import get_settings

logger = logging.getLogger("orchestrator.skills.fetch_url")
settings = get_settings()

MAX_CONTENT_CHARS = 5000
REQUEST_TIMEOUT = 15.0

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (compatible; Balbes-Agent/1.0; +https://github.com/balbes)"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.8",
}


def _html_to_text(html: str) -> str:
    """Convert HTML to readable plain text."""
    try:
        import html2text

        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        converter.body_width = 0
        converter.protect_links = True
        return converter.handle(html)
    except ImportError:
        pass

    # Fallback: basic regex stripping
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


async def fetch_url(
    url: str,
    http_client: httpx.AsyncClient | None = None,
    max_chars: int = MAX_CONTENT_CHARS,
) -> str:
    """
    Fetch URL content and return as clean text.

    Args:
        url: URL to fetch
        http_client: Optional shared httpx client
        max_chars: Maximum characters to return

    Returns:
        Cleaned text content, truncated to max_chars
    """
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True)

    try:
        response = await client.get(url, headers=HEADERS)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "html" in content_type:
            text = _html_to_text(response.text)
        else:
            text = response.text

        text = text.strip()
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[... content truncated at {max_chars} chars ...]"

        logger.info(f"Fetched {url}: {len(text)} chars")
        return text

    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error fetching {url}: {e.response.status_code}")
        return f"Failed to fetch {url}: HTTP {e.response.status_code}"
    except httpx.RequestError as e:
        logger.warning(f"Request error fetching {url}: {e}")
        return f"Failed to fetch {url}: {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {e}")
        return f"Error fetching {url}: {str(e)}"
    finally:
        if own_client:
            await client.aclose()
