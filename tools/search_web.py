import httpx
import asyncio
from typing import List, Dict, Any
from utils.logger import get_logger
from config.settings import settings

logger = get_logger()

# Simple query cache to avoid redundant hits in the same execution wave
_search_cache = {}

# Tool metadata for ToolRegistry auto-discovery
TOOL_META = {
    "name": "search_web",
    "aliases": ["web_search", "search", "google"],
    "class_name": "WebSearch",
    "description": "Web Search Engine: Performs web searches using multiple engines (DuckDuckGo, Google, Bing) with automatic fallback. Returns search results with titles, URLs, and snippets.",
    "enabled": True,
    "author": "Karatos Core",
    "version": "1.0.0",
    "actions": [
        {
            "name": "search_web",
            "description": "Search the web for information. Returns structured results with answer snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query to execute."},
                    "max_results": {"type": "integer", "description": "Maximum number of results (default: 5)."},
                    "search_depth": {"type": "string", "description": "Search depth: 'basic' or 'advanced'."}
                },
                "required": ["query"]
            }
        }
    ]
}


class WebSearch:
    """Wrapper class for unified dispatch."""

    @classmethod
    async def execute(cls, query: str = "", max_results: int = 5, search_depth: str = "basic", **kwargs) -> Dict[str, Any]:
        """Unified entry point for dynamic dispatch."""
        if not query:
            return {"status": "error", "message": "Missing 'query' parameter for web search."}
        return await search_web(query, max_results=max_results, search_depth=search_depth)


async def search_web(query: str, max_results: int = 5, search_depth: str = "basic") -> Dict[str, Any]:
    """
    Perform a web search with multi-engine support and Playwright fallback.
    Returns: {"answer": str or None, "results": List[Dict]}
    """
    # Check cache first
    cache_key = f"{query.lower().strip()}:{max_results}:{search_depth}"
    if cache_key in _search_cache:
        logger.debug(f"[SEARCH_WEB] Cache Hit for: {query}")
        return _search_cache[cache_key]

    logger.info(f"[SEARCH_WEB] Starting {search_depth} search for: {query}")
    final_response = {"answer": None, "results": []}
    
    # Phase -1: Tavily AI Search (MCP / Library Bridge) - Highest Priority
    tavily_api_key = settings.tavily_api_key
    if tavily_api_key:
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=tavily_api_key)
            response = client.search(
                query=query, 
                max_results=max_results, 
                include_answer=True,
                search_depth=search_depth
            )
            
            # Extract consolidation
            final_response["answer"] = response.get("answer")
            
            for res in response.get("results", []):
                final_response["results"].append({
                    "title": res['title'],
                    "link": res['url'],
                    "snippet": res['content']
                })
            
            if final_response["results"] or final_response["answer"]:
                _search_cache[cache_key] = final_response
                return final_response
                
        except Exception as e:
            pass
    
    # Phase 0: Google Search
    google_results = await _search_google_robust(query, max_results)
    
    if google_results:
        final_response["results"] = google_results
        _search_cache[cache_key] = final_response
        return final_response
        
    # Phase 1: DuckDuckGo Lite (Fast, HTTP only - Fallback)
    results = await _search_duckduckgo_lite(query, max_results)
    
    if results:
        return results
        
    # Phase 2: Bing Fallback (Robust, handles JS/Anti-bot)
    results = await _search_bing_robust(query, max_results)
    
    if not results:
        logger.warning(f"[SEARCH_WEB] Both search methods failed for: {query}")
        
    return results

async def _search_duckduckgo_lite(query: str, max_results: int) -> List[Dict[str, str]]:
    """Fast search using DuckDuckGo's HTML-only version."""
    url = "https://html.duckduckgo.com/html/"
    params = {"q": query}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, headers=headers) as client:
            response = await client.post(url, data=params, timeout=10.0)
            if response.status_code != 200 or "ddg-captcha" in response.text.lower():
                return []
                
            results = []
            import re
            # Extract result blocks
            blocks = re.findall(r'<div class="result.*?">.*?</div>', response.text, re.DOTALL)
            for block in blocks[:max_results]:
                link_match = re.search(r'class="result__a"\s+href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
                snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
                
                if link_match:
                    url_match = link_match.group(1)
                    title = re.sub(r'<[^>]+>', '', link_match.group(2)).strip()
                    
                    # Handle DDG outgoing link format
                    if "/l/?uddg=" in url_match:
                        from urllib.parse import unquote
                        url_match = unquote(url_match.split("uddg=")[1].split("&")[0])
                    
                    # --- NEW: Ad Filter ---
                    ad_patterns = [
                        "duckduckgo.com/y.js", "ad_domain=", "googleads", "doubleclick",
                        "clickserve", "ad-delivery", "partners", "sponsored", "promo",
                        "tracking", "affiliate", "marketing"
                    ]
                    if any(p in url_match.lower() for p in ad_patterns):
                        continue
                        
                    results.append({
                        "title": title,
                        "link": url_match,
                        "snippet": re.sub(r'<[^>]+>', '', snippet_match.group(1)).strip() if snippet_match else ""
                    })
            return results
    except Exception as e:
        logger.error(f"[SEARCH_WEB] Lite search error: {e}")
        return []

async def _search_google_robust(query: str, max_results: int) -> List[Dict[str, str]]:
    """Search using Google via Playwright with anti-detection."""
    from playwright.async_api import async_playwright
    
    results = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # Google Search
            search_url = f"https://www.google.com/search?q={query}&num={max_results + 3}"
            
            # --- NEW: Specific stealth for Search ---
            from playwright_stealth import stealth_async
            await stealth_async(page)
            
            await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            
            # Wait for results to appear
            try:
                await page.wait_for_selector("div.g", timeout=5000)
            except:
                pass

            # Extract results
            items = await page.query_selector_all("div.g")
            for item in items[:max_results]:
                title_elem = await item.query_selector("h3")
                link_elem = await item.query_selector("a")
                # Snippet is usually in a div with specific classes or the first div with text after title
                snippet_elem = await item.query_selector("div[style*='-webkit-line-clamp']") # Common for modern snippet
                if not snippet_elem:
                    snippet_elem = await item.query_selector("div.VwiC3b, .VwiC3b") # Fallback
                
                if title_elem and link_elem:
                    title = await title_elem.inner_text()
                    link = await link_elem.get_attribute("href")
                    snippet = await snippet_elem.inner_text() if snippet_elem else ""
                    
                    if link and link.startswith("http"):
                        results.append({
                            "title": title,
                            "link": link,
                            "snippet": snippet
                        })
            
            await browser.close()
    except Exception as e:
        logger.error(f"[SEARCH_GOOGLE] Google search failed: {e}")
        
    return results

async def _search_bing_robust(query: str, max_results: int) -> List[Dict[str, str]]:
    """Search using Bing via Playwright (Reliable Fallback)."""
    from playwright.async_api import async_playwright
    
    results = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            # --- NEW: Specific stealth for Search ---
            from playwright_stealth import stealth_async
            await stealth_async(page)
            
            # Using Bing as it's generally more stable for automated headless access than Google
            search_url = f"https://www.bing.com/search?q={query}"
            
            await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            
            # Extract results
            items = await page.query_selector_all("li.b_algo")
            for item in items[:max_results]:
                title_elem = await item.query_selector("h2 a")
                snippet_elem = await item.query_selector("p, .b_caption")
                
                if title_elem:
                    title = await title_elem.inner_text()
                    link = await title_elem.get_attribute("href")
                    snippet = await snippet_elem.inner_text() if snippet_elem else ""
                    results.append({
                        "title": title,
                        "link": link,
                        "snippet": snippet
                    })
            
            await browser.close()
    except Exception as e:
        logger.error(f"[SEARCH_BING] Bing search failed: {e}")
        
    return results

if __name__ == "__main__":
    async def test():
        data = await search_web("Gold price today in Vietnam")
        if data.get("answer"):
            print(f"AI ANSWER: {data['answer']}\n")
        print("SEARCH RESULTS:")
        for r in data.get("results", []):
            print(f"- {r['title']}: {r['link']}")
    asyncio.run(test())
