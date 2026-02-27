"""
Web Scraper Tool — Adaptive Web Content Extraction using Scrapling.
Uses Scrapling framework for: fast HTTP requests, stealth anti-bot bypassing,
and full dynamic JS rendering — all with a unified CSS/XPath selector API.
"""
import asyncio
import re
import json
from typing import Any, Dict, List, Optional
from utils.logger import get_logger

logger = get_logger()

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "web_scraper",
    "aliases": ["scrape", "scrape_url", "fetch_page", "summarize_url", "summarize_web", "tóm tắt website"],
    "class_name": "WebScraper",
    "description": "Web Scraper: Fetches and extracts content from web pages using Scrapling. Supports fast HTTP, stealth mode (anti-bot bypass), and full JS rendering. Extracts text, HTML, links, or structured data with CSS/XPath selectors.",
    "actions": [
        {
            "name": "scrape_url",
            "description": "Fetch a URL and extract its content or SUMMARIZE the webpage content.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to scrape."},
                    "extract_mode": {"type": "string", "description": "Mode: 'text' (clean text), 'html' (raw HTML), 'links' (all links), 'structured' (headings + paragraphs). Default: text."},
                    "css_selector": {"type": "string", "description": "Optional CSS selector to extract specific elements."},
                    "use_stealth": {"type": "boolean", "description": "Use stealth mode for anti-bot sites (default: false)."},
                    "use_dynamic": {"type": "boolean", "description": "Use full browser for JS-rendered pages (default: false)."},
                    "timeout": {"type": "integer", "description": "Request timeout in seconds (default: 15)."}
                },
                "required": ["url"]
            }
        }
    ]
}


def _ensure_scrapling():
    """Auto-install scrapling if not present."""
    try:
        import scrapling
        return True
    except ImportError:
        import subprocess, sys
        logger.info("[WEB_SCRAPER] Installing scrapling[all]...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "scrapling[all]", "-q"])
        # Install browser dependencies
        try:
            subprocess.check_call([sys.executable, "-m", "scrapling", "install"], timeout=120)
        except Exception as e:
            logger.warning(f"[WEB_SCRAPER] Browser install skipped: {e}")
        return True


class WebScraper:
    """Adaptive web content extractor using Scrapling framework."""

    # Sites that typically require stealth/dynamic rendering
    REQUIRES_STEALTH = {"twitter.com", "x.com", "instagram.com", "facebook.com", "linkedin.com"}
    REQUIRES_DYNAMIC = {"instagram.com", "facebook.com"}

    @classmethod
    async def execute(cls, url: str = "", **kwargs) -> Dict[str, Any]:
        """Unified entry point for dynamic dispatch."""
        if not url:
            return {"status": "error", "message": "Missing 'url' parameter."}
        return await cls.scrape(url=url, **kwargs)

    @classmethod
    async def scrape(cls, url: str, extract_mode: str = "text",
                     css_selector: str = None, use_stealth: bool = False,
                     use_dynamic: bool = False, timeout: int = 15) -> Dict[str, Any]:
        """Scrape a URL and return extracted content."""
        _ensure_scrapling()
        
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.hostname or ""
        
        # Specifically for Facebook: use m.facebook.com to bypass some JS-heavy blocks
        # Only do this if it's a www link and not already a mobile link
        if "facebook.com" in domain and not domain.startswith("m.") and not domain.startswith("mbasic."):
             url = url.replace("www.facebook.com", "m.facebook.com").replace("facebook.com", "m.facebook.com")
             domain = "m.facebook.com"
        
        # Auto-detect mode based on domain
        if domain in cls.REQUIRES_DYNAMIC:
            use_dynamic = True
        elif domain in cls.REQUIRES_STEALTH:
            use_stealth = True

        # Run in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        try:
            if use_dynamic:
                result = await loop.run_in_executor(
                    None, cls._scrape_dynamic, url, extract_mode, css_selector, timeout
                )
            elif use_stealth:
                result = await loop.run_in_executor(
                    None, cls._scrape_stealth, url, extract_mode, css_selector, timeout
                )
            else:
                result = await loop.run_in_executor(
                    None, cls._scrape_fast, url, extract_mode, css_selector, timeout
                )
            return result
        except Exception as e:
            logger.error(f"[WEB_SCRAPER] Scrape failed: {e}")
            return {"status": "error", "message": str(e), "url": url}

    @classmethod
    def _scrape_fast(cls, url: str, mode: str, selector: str,
                     timeout: int) -> Dict[str, Any]:
        """Fast scraping with Scrapling Fetcher (no JS, no stealth)."""
        from scrapling.fetchers import Fetcher
        
        try:
            page = Fetcher.get(url, stealthy_headers=True, timeout=timeout)
            return cls._extract_content(page, url, mode, selector)
        except Exception as e:
            return {"status": "error", "message": f"Fast fetch failed: {str(e)}", "url": url}

    @classmethod
    def _scrape_stealth(cls, url: str, mode: str, selector: str,
                        timeout: int) -> Dict[str, Any]:
        """Stealth scraping — bypasses anti-bot protections."""
        from scrapling.fetchers import StealthyFetcher

        try:
            page = StealthyFetcher.fetch(url, headless=True, timeout=timeout * 1000)
            return cls._extract_content(page, url, mode, selector)
        except Exception as e:
            logger.warning(f"[WEB_SCRAPER] Stealth failed, falling back to fast: {e}")
            return cls._scrape_fast(url, mode, selector, timeout)

    @classmethod
    def _scrape_dynamic(cls, url: str, mode: str, selector: str,
                        timeout: int) -> Dict[str, Any]:
        """Full browser rendering for JS-heavy pages."""
        from scrapling.fetchers import DynamicFetcher

        try:
            page = DynamicFetcher.fetch(
                url, headless=True, 
                network_idle=True, timeout=timeout * 1000
            )
            return cls._extract_content(page, url, mode, selector)
        except Exception as e:
            logger.warning(f"[WEB_SCRAPER] Dynamic failed, falling back to stealth: {e}")
            return cls._scrape_stealth(url, mode, selector, timeout)

    @classmethod
    def _extract_content(cls, page, url: str, mode: str,
                         selector: str = None) -> Dict[str, Any]:
        """Extract content from a Scrapling page response."""
        
        # Get page title
        title_els = page.css("title::text")
        title = title_els.get() if title_els else ""

        # Apply CSS selector filter if specified
        if selector:
            elements = page.css(selector)
            if not elements:
                return {"status": "error", "message": f"No elements match selector: {selector}", "url": url}

        if mode == "html":
            # Raw HTML extraction
            if selector:
                content = "".join(str(el) for el in page.css(selector))
            else:
                content = str(page.body)
            content = content[:20000]
            return {"status": "success", "url": url, "title": title, "content": content, "type": "html"}

        elif mode == "links":
            # Extract all links
            links = []
            for a in page.css("a"):
                href = a.attrib.get("href", "")
                text = a.css("::text").get() or ""
                text = text.strip()[:100]
                if href and (href.startswith("http") or href.startswith("/")):
                    links.append({"text": text, "href": href})
            return {"status": "success", "url": url, "title": title, "links": links[:100], "type": "links"}

        elif mode == "structured":
            # Headings + paragraphs structure
            sections = []
            for heading in page.css("h1, h2, h3, h4"):
                heading_text = heading.css("::text").get() or ""
                heading_text = heading_text.strip()
                
                # Get heading level from tag name
                tag_name = heading.tag if hasattr(heading, 'tag') else "h2"
                level = int(tag_name[1]) if tag_name and tag_name[0] == 'h' else 2
                
                sections.append({
                    "heading": heading_text,
                    "level": level,
                })
            return {"status": "success", "url": url, "title": title, "sections": sections[:30], "type": "structured"}

        else:  # text mode (default)
            # Clean text extraction — remove scripts, styles, nav, footer
            # Use Scrapling's built-in text extraction
            if selector:
                text_parts = page.css(f"{selector}::text").getall()
                text = "\n".join(t.strip() for t in text_parts if t.strip())
            else:
                # Remove noise elements first
                text_parts = []
                for el in page.css("body *:not(script):not(style):not(nav):not(footer):not(header):not(aside)"):
                    el_text = el.css("::text").get()
                    if el_text and el_text.strip():
                        text_parts.append(el_text.strip())
                
                # Fallback: get all text from body
                if not text_parts:
                    all_text = page.css("body::text").getall()
                    text_parts = [t.strip() for t in all_text if t.strip()]
                
                text = "\n".join(text_parts)
            
            # Clean up excessive whitespace
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text[:15000]
            word_count = len(text.split())
            
            return {"status": "success", "url": url, "title": title,
                    "content": text, "word_count": word_count, "type": "text"}
