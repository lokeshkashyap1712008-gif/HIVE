"""
HIVE — Web Scout Worker
HTTP requests, API calls, scraping, form fills, session management.
Now includes Exa AI search for web queries without URLs.
"""

import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)


class WebScout:
    @staticmethod
    async def run(description: str, context: dict = None) -> dict:
        description_lower = description.lower()
        context = context or {}

        try:
            import re

            # Check if there's a URL in the task
            url_match = re.search(r"https?://[^\s]+", description)
            url = url_match.group(0).rstrip(".,;") if url_match else None

            if not url:
                url = _extract_url(description)

            # If no URL, use Exa search
            if not url:
                return await _exa_search_from_description(description)

            # URL-based operations
            if any(word in description_lower for word in ["login", "sign in", "authenticate"]):
                result = await _handle_login(url, description)
            elif any(word in description_lower for word in ["api", "endpoint", "json", "rest"]):
                result = await _call_api(url, description)
            elif any(word in description_lower for word in ["crawl", "scrape", "find links", "sitemap"]):
                result = await _crawl_site(url, description)
            elif any(word in description_lower for word in ["form", "submit", "post data"]):
                result = await _submit_form(url, description)
            elif any(word in description_lower for word in ["check", "verify", "status", "health"]):
                result = await _health_check(url)
            else:
                result = await _fetch_page(url)

            return result

        except Exception as e:
            logger.error(f"[WebScout] Error: {e}")
            return {"status": "error", "error": str(e)}


async def _exa_search_from_description(description: str) -> dict:
    """Use Exa AI to search when no URL is provided."""
    api_key = os.environ.get("EXA_API_KEY", "")
    if not api_key:
        return {"status": "error", "error": "No URL found and EXA_API_KEY not set. Cannot search."}

    url = "https://api.exa.ai/search"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }

    # Extract search query and any domain hints from description
    query = description.strip()
    include_domains = []

    # Check for domain hints like "from google maps" or "on yelp"
    domain_map = {
        "google maps": ["google.com/maps", "maps.google.com"],
        "yelp": ["yelp.com"],
        "yellow pages": ["yellowpages.com"],
        "justdial": ["justdial.com"],
        "zomato": ["zomato.com"],
        "swiggy": ["swiggy.com"],
        "linkedin": ["linkedin.com"],
        "github": ["github.com"],
    }

    desc_lower = description.lower()
    for hint, domains in domain_map.items():
        if hint in desc_lower:
            include_domains.extend(domains)

    payload = {
        "query": query,
        "numResults": 10,
        "type": "auto",
        "contents": {
            "text": True,
        },
    }

    if include_domains:
        payload["includeDomains"] = include_domains

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=payload, headers=headers, timeout=30.0)
            if resp.status_code != 200:
                return {"status": "error", "error": f"Exa API error: {resp.status_code}"}

            data = resp.json()
            results = []
            for r in data.get("results", []):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "published_date": r.get("publishedDate", ""),
                    "author": r.get("author", ""),
                    "text": r.get("text", "")[:3000],
                })

            return {
                "status": "success",
                "source": "exa_search",
                "query": query,
                "domains_searched": include_domains or ["all"],
                "results": results,
                "total": len(results),
            }

        except httpx.TimeoutException:
            return {"status": "error", "error": "Exa API request timed out"}
        except Exception as e:
            return {"status": "error", "error": f"Exa search failed: {str(e)}"}


async def _fetch_page(url: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content = resp.text[:2000]

    import re
    title = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
    return {
        "status": "success",
        "url": url,
        "http_status": resp.status_code,
        "title": title.group(1) if title else "No title",
        "content_preview": content[:500],
        "content_length": len(resp.text),
    }


async def _health_check(url: str) -> dict:
    import time as _time
    async with httpx.AsyncClient(timeout=10.0) as client:
        start = _time.time()
        resp = await client.get(url)
        elapsed = (_time.time() - start) * 1000

    return {
        "status": "success",
        "url": url,
        "http_status": resp.status_code,
        "response_time_ms": round(elapsed, 1),
        "content_type": resp.headers.get("content-type", "unknown"),
        "server": resp.headers.get("server", "unknown"),
    }


async def _call_api(url: str, description: str) -> dict:
    method = "GET"
    if any(word in description.lower() for word in ["post", "create", "submit"]):
        method = "POST"
    elif any(word in description.lower() for word in ["put", "update", "edit"]):
        method = "PUT"
    elif any(word in description.lower() for word in ["delete", "remove"]):
        method = "DELETE"

    async with httpx.AsyncClient(timeout=15.0) as client:
        if method == "GET":
            resp = await client.get(url)
        elif method == "POST":
            resp = await client.post(url, json={"example": "data"})
        elif method == "PUT":
            resp = await client.put(url, json={"example": "data"})
        else:
            resp = await client.delete(url)

    try:
        data = resp.json()
        return {
            "status": "success",
            "method": method,
            "url": url,
            "http_status": resp.status_code,
            "response": data if isinstance(data, dict) else {"data": data},
        }
    except Exception:
        return {
            "status": "success",
            "method": method,
            "url": url,
            "http_status": resp.status_code,
            "response_preview": resp.text[:500],
        }


async def _crawl_site(url: str, description: str) -> dict:
    import re

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url)
        content = resp.text

    links = re.findall(r'href=["\'](https?://[^"\']+)["\']', content)
    links = list(set(links))[:20]

    description_tag = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', content, re.IGNORECASE)

    return {
        "status": "success",
        "url": url,
        "links_found": len(links),
        "sample_links": links[:10],
        "meta_description": description_tag.group(1) if description_tag else None,
        "page_count_estimate": len(links) * 5,
    }


async def _handle_login(url: str, description: str) -> dict:
    import re
    user_match = re.search(r"(?:user|username|email)[:\s]+(\S+@\S+|\w+)", description, re.IGNORECASE)
    pass_match = re.search(r"(?:pass|password)[:\s]+(\S+)", description, re.IGNORECASE)

    if not user_match or not pass_match:
        return {
            "status": "skipped",
            "reason": "No credentials provided in task description",
            "tip": "Include username and password in the task description",
        }

    username = user_match.group(1)
    password = pass_match.group(1)

    async with httpx.AsyncClient(timeout=15.0) as client:
        login_url = url.rstrip("/") + "/login"
        try:
            resp = await client.get(login_url)
            import re
            username_field = re.search(r'name=["\']([^"\']*(?:user|email|login)[^"\']*)["\']', resp.text, re.IGNORECASE)
            password_field = re.search(r'name=["\']([^"\']*(?:pass|pwd|secret)[^"\']*)["\']', resp.text, re.IGNORECASE)

            if username_field and password_field:
                form_data = {username_field.group(1): username, password_field.group(1): password}
                login_resp = await client.post(login_url, data=form_data)
                return {
                    "status": "success",
                    "url": login_url,
                    "login_attempted": True,
                    "response_code": login_resp.status_code,
                    "session_cookies": list(login_resp.cookies.keys()),
                }
        except Exception:
            pass

    return {"status": "skipped", "reason": "Could not find login form", "url": url}


async def _submit_form(url: str, description: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        import re
        fields = re.findall(r'<input[^>]+name=["\']([^"\']+)["\']', resp.text)
        form_data = {f: f"test_{f}" for f in fields[:5]}
        submit_resp = await client.post(url, data=form_data)
        return {
            "status": "success",
            "url": url,
            "fields_submitted": len(form_data),
            "response_code": submit_resp.status_code,
        }


def _extract_url(description: str) -> Optional[str]:
    import re
    url = re.search(r"https?://[^\s]+", description)
    return url.group(0).rstrip(".,;") if url else None


async def run(description: str, context: dict = None) -> dict:
    return await WebScout.run(description, context)
