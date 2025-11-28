# extractors/tiktok.py
import re
import json
from typing import Optional, Tuple
from bs4 import BeautifulSoup

from utils.http import http_get
from extractors.base import get_meta_content
from utils.selenium_utils import (
    create_driver,
    quit_driver,
    load_tiktok_page,
    extract_tiktok_media
)
from utils.normalize import normalize_title, normalize_subtitle

DEFAULT_PLACEHOLDER = "https://dummyimage.com/600x400/e0e0e0/555.png&text=No+Image"


def extract_tiktok_id(url: str) -> Optional[str]:
    """Extract TikTok video ID from various URL formats."""
    patterns = [
        r'tiktok\.com/@[^/]+/video/(\d+)',
        r'tiktok\.com/v/(\d+)',
        r'vm\.tiktok\.com/([A-Za-z0-9]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


async def get_tiktok_metadata(url: str) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract title, subtitle, media URL, content, and media type from a TikTok URL.
    Returns (title, subtitle, media_url, content, media_type)
    """
    print(f"DEBUG - get_tiktok_metadata called with: {url}")

    driver = None
    try:
        video_id = extract_tiktok_id(url)
        if video_id:
            print(f"DEBUG - TikTok video ID: {video_id}")
        else:
            print(f"DEBUG - Could not extract video ID from: {url}")

        # Create driver for Selenium extraction
        driver = await create_driver()

        # Load page with Selenium
        page_source = await load_tiktok_page(driver, url)
        soup = BeautifulSoup(page_source, 'html.parser')

        # Initialize variables
        media_url = None
        media_type = "video"
        title = None
        subtitle = None
        content = None

        # ============ EXTRACT MEDIA WITH SELENIUM ============
        media_url, media_type = await extract_tiktok_media(driver)

        # ============ EXTRACT METADATA FROM PAGE SOURCE ============
        # Try to parse SIGI_STATE JSON for reliable data
        script_tag = soup.find("script", id="SIGI_STATE")
        if script_tag:
            try:
                data = json.loads(script_tag.string)

                # Navigate through the nested structure
                item_module = data.get("ItemModule", {})
                if item_module:
                    item = list(item_module.values())[0]

                    # Title / description
                    title = normalize_title(item.get("desc", "TikTok Video"))

                    # Subtitle / author
                    author_data = item.get('author')
                    if isinstance(author_data, dict):
                        username = author_data.get('uniqueId', 'TikTok')
                    else:
                        username = 'TikTok'
                    subtitle = normalize_subtitle(f"@{username}")

                    # Content: same as title
                    content = title

                    print(f"DEBUG - Extracted from SIGI_STATE: title={title[:50]}, subtitle={subtitle}")

            except Exception as e:
                print(f"DEBUG - Failed SIGI_STATE parsing: {e}")
                import traceback
                traceback.print_exc()

        # Fallback: use meta tags if JSON fails
        if not title:
            title = normalize_title(
                get_meta_content(soup, 'og:title') or
                get_meta_content(soup, 'twitter:title', attr='name') or
                "TikTok Video"
            )

        if not subtitle:
            # Try to extract username from URL
            username_match = re.search(r'tiktok\.com/@([^/]+)', url)
            if username_match:
                subtitle = normalize_subtitle(f"@{username_match.group(1)}")
            else:
                subtitle = normalize_subtitle(
                    get_meta_content(soup, 'og:site_name') or "TikTok"
                )

        if not content:
            content = get_meta_content(soup, 'og:description') or title

        # If Selenium didn't find media, try meta tags
        if not media_url or media_url == DEFAULT_PLACEHOLDER:
            print(f"DEBUG - Falling back to meta tag extraction for media")

            # Try og:image for cover
            cover_url = get_meta_content(soup, 'og:image')
            if cover_url:
                print(f"DEBUG - Found og:image: {cover_url[:100]}")
                media_url = cover_url
            else:
                media_url = DEFAULT_PLACEHOLDER

        # Use placeholder if still nothing found
        if not media_url:
            print(f"DEBUG - No media URL found, using placeholder")
            media_url = DEFAULT_PLACEHOLDER

        print(f"DEBUG - FINAL: title={title[:50]}, subtitle={subtitle}, media_type={media_type}")
        print(f"DEBUG - FINAL: media_url={media_url[:100] if media_url else None}")

        return title, subtitle, media_url, content, media_type

    except Exception as e:
        print(f"ERROR in get_tiktok_metadata: {e}")
        import traceback
        traceback.print_exc()
        return None, None, DEFAULT_PLACEHOLDER, url, "video"

    finally:
        # Clean up driver
        if driver:
            await quit_driver(driver)