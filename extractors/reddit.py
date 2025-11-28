import asyncio
import json
import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup
import httpx

from utils.text import extract_urls_from_text
from utils.normalize import normalize_title, normalize_subtitle
from extractors.base import get_meta_content

DEFAULT_PLACEHOLDER = "https://dummyimage.com/600x400/e0e0e0/555.png&text=No+Image"


def normalize_reddit_url(url: str) -> str:
    """
    Normalize any Reddit URL to the standard format.
    Handles old.reddit.com, www.reddit.com, redd.it, etc.
    """
    # Remove query parameters and fragments
    url = url.split('?')[0].split('#')[0]

    # Handle redd.it short links
    if 'redd.it' in url:
        return url  # These redirect automatically

    # Ensure www.reddit.com format
    url = url.replace('old.reddit.com', 'www.reddit.com')

    # Remove trailing slashes
    url = url.rstrip('/')

    return url


async def resolve_reddit_search_link(url: str) -> Optional[str]:
    """
    Resolves a /s/... search link to the first /comments/... URL in the HTML.
    Returns None if cannot resolve.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                print(f"DEBUG - Could not fetch search page: {resp.status_code}")
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            # Try multiple selectors for finding the post link
            selectors = [
                'a[href*="/comments/"]',
                'a[data-click-id="body"]',
                'shreddit-post a[slot="full-post-link"]'
            ]

            for selector in selectors:
                link = soup.select_one(selector)
                if link and link.get("href"):
                    href = link["href"]
                    if href.startswith("/"):
                        href = f"https://www.reddit.com{href}"
                    print(f"DEBUG - Resolved /s/ link to: {href}")
                    return href

    except Exception as e:
        print(f"DEBUG - Error resolving search link: {e}")
        import traceback
        traceback.print_exc()
    return None


def extract_reddit_post_id(url: str) -> Optional[str]:
    """Extract Reddit post ID from any /comments/... URL."""
    match = re.search(r'/comments/([a-z0-9]+)', url)
    if match:
        return match.group(1)
    return None


async def get_reddit_metadata(url: str) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract title, author (subtitle), media_url, content, media_type from any Reddit URL.
    Works for /comments/..., /s/... and redd.it short links.
    Returns: (title, subtitle, media_url, content, media_type)
    """
    try:
        print(f"DEBUG - Processing Reddit URL: {url}")

        # Handle /s/... links by resolving to a canonical post
        if "/s/" in url:
            print("DEBUG - Detected /s/ link, resolving...")
            resolved = await resolve_reddit_search_link(url)
            if resolved:
                url = resolved
            else:
                print("DEBUG - Could not resolve /s/ link")
                return None, None, None, None, None

        # Handle redd.it short links by following redirects
        if 'redd.it' in url:
            print("DEBUG - Detected redd.it short link, following redirect...")
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.head(url)
                url = str(resp.url)
                print(f"DEBUG - Redirected to: {url}")

        # Normalize the URL
        url = normalize_reddit_url(url)

        # Ensure we have a /comments/ URL
        if '/comments/' not in url:
            print(f"DEBUG - URL doesn't contain /comments/: {url}")
            return None, None, None, None, None

        # Build JSON endpoint URL
        json_url = url.rstrip("/") + ".json"
        print(f"DEBUG - Fetching JSON from: {json_url}")

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; RedditExtractor/1.0)"
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(json_url, headers=headers)
            if resp.status_code != 200:
                print(f"DEBUG - Reddit JSON fetch failed: {resp.status_code}")
                print(f"DEBUG - Response: {resp.text[:200]}")
                return None, None, None, None, None

            data = resp.json()
            print(f"DEBUG - JSON response type: {type(data)}")

        # Validate response structure
        if not data or not isinstance(data, list) or len(data) == 0:
            print(f"DEBUG - Invalid JSON structure: {type(data)}")
            return None, None, None, None, None

        # Extract post data
        try:
            post_listing = data[0]
            if 'data' not in post_listing or 'children' not in post_listing['data']:
                print(f"DEBUG - Missing data/children in response")
                return None, None, None, None, None

            children = post_listing['data']['children']
            if not children or len(children) == 0:
                print(f"DEBUG - No children in post listing")
                return None, None, None, None, None

            post_data = children[0]['data']
            print(f"DEBUG - Successfully extracted post data")

        except (KeyError, IndexError, TypeError) as e:
            print(f"DEBUG - Error extracting post data: {e}")
            return None, None, None, None, None

        # Extract metadata
        title = normalize_title(post_data.get("title", ""))
        author = post_data.get("author", "")
        subtitle = normalize_subtitle(f"u/{author}" if author else "")
        content = post_data.get("selftext", "")

        media_url = None
        media_type = "image"

        # Determine media URL and type
        print(f"DEBUG - Post hint: {post_data.get('post_hint')}")
        print(f"DEBUG - Is gallery: {post_data.get('is_gallery')}")
        print(f"DEBUG - URL: {post_data.get('url')}")

        # Check for hosted video
        if post_data.get("is_video") or post_data.get("post_hint") == "hosted:video":
            reddit_video = post_data.get("media", {}).get("reddit_video", {})
            media_url = reddit_video.get("fallback_url") or reddit_video.get("dash_url")
            media_type = "video"
            print(f"DEBUG - Found hosted video: {media_url}")

        # Check for image
        elif post_data.get("post_hint") == "image":
            media_url = post_data.get("url")
            media_type = "image"
            print(f"DEBUG - Found image: {media_url}")

        # Check for gallery
        elif post_data.get("is_gallery"):
            media_metadata = post_data.get("media_metadata", {})
            gallery_data = post_data.get("gallery_data", {})

            if media_metadata:
                # Get first image from gallery
                first_item_id = next(iter(media_metadata.keys()), None)
                if first_item_id:
                    first_item = media_metadata[first_item_id]
                    # Try different sources for the image URL
                    media_url = (
                            first_item.get("s", {}).get("u") or
                            first_item.get("s", {}).get("gif") or
                            first_item.get("p", [{}])[-1].get("u")
                    )
                    if media_url:
                        # Decode HTML entities in URL
                        media_url = media_url.replace("&amp;", "&")
                    media_type = "image"
                    print(f"DEBUG - Found gallery image: {media_url}")

        # Check for preview images
        elif post_data.get("preview"):
            images = post_data.get("preview", {}).get("images", [])
            if images:
                source = images[0].get("source", {})
                media_url = source.get("url")
                if media_url:
                    media_url = media_url.replace("&amp;", "&")
                media_type = "image"
                print(f"DEBUG - Found preview image: {media_url}")

        # Fallback to thumbnail
        elif post_data.get("thumbnail") and post_data["thumbnail"].startswith("http"):
            media_url = post_data["thumbnail"]
            media_type = "image"
            print(f"DEBUG - Using thumbnail: {media_url}")

        # Check direct URL
        elif post_data.get("url"):
            url_str = post_data["url"]
            # Check if it's an image or video
            if any(url_str.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                media_url = url_str
                media_type = "image"
                print(f"DEBUG - Found direct image URL: {media_url}")
            elif any(url_str.endswith(ext) for ext in ['.mp4', '.webm', '.mov']):
                media_url = url_str
                media_type = "video"
                print(f"DEBUG - Found direct video URL: {media_url}")

        # Use placeholder if no media found
        if not media_url or media_url == "self" or media_url == "default":
            media_url = DEFAULT_PLACEHOLDER
            media_type = "image"
            print(f"DEBUG - Using placeholder image")

        print(
            f"DEBUG - Final metadata: title={title[:50]}..., author={subtitle}, media={media_url}, content_len={len(content)}, type={media_type}")
        return title, subtitle, media_url, content, media_type

    except Exception as e:
        print(f"Error in get_reddit_metadata: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None, None, None