# extractors/instagram.py
import re
import json
from typing import Optional, Tuple
from bs4 import BeautifulSoup

from extractors.base import get_meta_content
from utils.selenium_utils import (
    create_driver,
    quit_driver,
    load_instagram_page,
    extract_media_from_selenium
)
from utils.normalize import normalize_title, normalize_subtitle

DEFAULT_PLACEHOLDER = "https://dummyimage.com/600x400/e0e0e0/555.png&text=No+Image"


def extract_instagram_id(url: str) -> Optional[str]:
    """Extract Instagram post ID from various URL formats."""
    patterns = [
        r'instagram\.com/p/([A-Za-z0-9_-]+)',
        r'instagram\.com/reel/([A-Za-z0-9_-]+)',
        r'instagram\.com/tv/([A-Za-z0-9_-]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_reel_url(url: str) -> bool:
    """Check if URL is a reel."""
    return '/reel/' in url


async def get_instagram_metadata(url: str) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract title, subtitle, media URL, content, and media type from an Instagram URL.
    Returns (title, subtitle, media_url, content, media_type)
    """
    print(f"DEBUG - get_instagram_metadata called with: {url}")

    # Handle kkinstagram URLs by converting to regular instagram
    if 'kkinstagram.com' in url:
        url = url.replace('kkinstagram.com', 'instagram.com')
        print(f"DEBUG - Converted kkinstagram URL to: {url}")

    driver = None
    try:
        # Extract post ID and check if it's a reel
        post_id = extract_instagram_id(url)
        if not post_id:
            print(f"DEBUG - Could not extract Instagram post ID")
            return None, None, None, None, None

        is_reel = is_reel_url(url)
        print(f"DEBUG - Extracted post ID: {post_id}, is_reel: {is_reel}")

        # Create driver
        driver = await create_driver()

        # Load page
        page_source = await load_instagram_page(driver, url)
        soup = BeautifulSoup(page_source, 'html.parser')

        # Initialize variables
        media_url = None
        media_type = "video" if is_reel else "image"

        # ============ EXTRACT MEDIA URL WITH SELENIUM ============
        media_url, media_type = await extract_media_from_selenium(driver, is_reel=is_reel)

        # For reels, try additional extraction methods
        if is_reel and not media_url:
            print(f"DEBUG - Attempting reel-specific extraction")

            # Try to find video element in page source with various patterns
            video_patterns = [
                r'"video_url":\s*"(https://[^"]+)"',
                r'"playback_url":\s*"(https://[^"]+)"',
                r'"src":\s*"(https://[^"]+\.mp4[^"]*)"',
                r'videoUrl":"(https://[^"]+)"',
            ]

            for pattern in video_patterns:
                matches = re.findall(pattern, page_source)
                if matches:
                    # Filter out thumbnail URLs (they often contain 'thumbnail' or have play buttons)
                    video_matches = [m for m in matches if 'thumbnail' not in m.lower()]
                    if video_matches:
                        # Get the longest/highest quality URL
                        media_url = max(video_matches, key=len).replace(r'\/', '/').replace('\\u0026', '&')
                        print(f"DEBUG - Found video URL via pattern: {media_url[:100]}")
                        media_type = "video"
                        break

        # Fallback to meta tags from page source
        if not media_url:
            print(f"DEBUG - Falling back to meta tag extraction")

            # For reels, prioritize video meta tags
            if is_reel:
                video_url = get_meta_content(soup, 'og:video') or get_meta_content(soup, 'og:video:secure_url')
                if video_url:
                    print(f"DEBUG - Found video URL in meta: {video_url[:100]}")
                    media_url = video_url
                    media_type = "video"

            # If no video found, try image
            if not media_url:
                image_url = get_meta_content(soup, 'og:image')
                if image_url:
                    print(f"DEBUG - Found og:image: {image_url[:100]}")
                    # For reels, only use og:image as absolute fallback and mark it appropriately
                    if is_reel:
                        # Check if this is a low-quality thumbnail (often has dimensions in URL)
                        if 'thumbnail' in image_url.lower() or 's150x150' in image_url or 's320x320' in image_url:
                            print(f"DEBUG - Skipping low-quality thumbnail for reel")
                        else:
                            media_url = image_url
                            # Keep as video type but we only have thumbnail
                    else:
                        media_url = image_url
                        media_type = "image"

        # Try JSON-LD structured data
        if not media_url:
            print(f"DEBUG - Trying JSON-LD extraction")
            for script_tag in soup.find_all("script", type="application/ld+json"):
                try:
                    json_data = json.loads(script_tag.string)
                    if isinstance(json_data, dict):
                        # For VideoObject
                        if json_data.get('@type') == 'VideoObject':
                            if 'contentUrl' in json_data:
                                media_url = json_data['contentUrl']
                                media_type = "video"
                                print(f"DEBUG - Found video in VideoObject: {media_url[:100]}")
                                break
                        # For general image/contentUrl
                        if 'image' in json_data:
                            img = json_data['image']
                            media_url = img[0] if isinstance(img, list) else img
                            print(f"DEBUG - Found image in JSON-LD: {media_url[:100]}")
                            break
                        if 'contentUrl' in json_data:
                            media_url = json_data['contentUrl']
                            print(f"DEBUG - Found contentUrl in JSON-LD: {media_url[:100]}")
                            break
                except Exception as e:
                    print(f"DEBUG - Error parsing JSON-LD: {e}")
                    continue

        # Try extracting from page scripts (display_url for images)
        if not media_url and not is_reel:
            print(f"DEBUG - Trying to extract from page scripts")
            script_pattern = r'"display_url":\s*"(https://[^"]+)"'
            matches = re.findall(script_pattern, page_source)
            if matches:
                # Get longest URL (usually full-size)
                media_url = max(matches, key=len).replace(r'\/', '/')
                print(f"DEBUG - Found display_url in scripts: {media_url[:100]}")
                media_type = "image"

        # For reels without video URL, try to get high-quality image
        if not media_url and is_reel:
            print(f"DEBUG - Trying to extract high-quality image for reel")
            # Try display_url which is usually higher quality
            display_pattern = r'"display_url":\s*"(https://[^"]+)"'
            matches = re.findall(display_pattern, page_source)
            if matches:
                # Filter out thumbnails and get highest quality
                hq_images = [m for m in matches if 'thumbnail' not in m.lower()
                             and 's150x150' not in m and 's320x320' not in m]
                if hq_images:
                    media_url = max(hq_images, key=len).replace(r'\/', '/')
                    print(f"DEBUG - Found high-quality display_url for reel: {media_url[:100]}")
                    media_type = "video"  # Keep as video type since it's a reel

        # Use placeholder if nothing found
        if not media_url:
            print(f"DEBUG - No media URL found, using placeholder")
            media_url = DEFAULT_PLACEHOLDER
            # Keep original media_type determination
            if not is_reel:
                media_type = "image"

        # ============ EXTRACT TITLE ============
        title = (
                get_meta_content(soup, 'og:title') or
                get_meta_content(soup, 'twitter:title', attr='name') or
                (soup.title.string.strip() if soup.title and soup.title.string else None)
        )

        if title:
            title = re.sub(r'\s*on Instagram.*$', '', title, flags=re.IGNORECASE)
            title = re.sub(r'\s*•\s*Instagram.*$', '', title, flags=re.IGNORECASE)

        if not title or title.lower().startswith('instagram'):
            description = get_meta_content(soup, 'og:description')
            if description:
                first_sentence = re.split(r'[.!?]', description)[0]
                title = first_sentence[:100] if len(first_sentence) > 100 else first_sentence

        title_suffix = "Instagram Reel" if is_reel else "Instagram Post"
        title = normalize_title(title or f"{title_suffix} {post_id}")

        # ============ EXTRACT SUBTITLE (USERNAME) ============
        subtitle = None

        username_match = re.search(r'instagram\.com/([^/]+)/', url)
        if username_match:
            subtitle = f"@{username_match.group(1)}"

        if not subtitle:
            author = get_meta_content(soup, 'author', attr='name')
            if author:
                subtitle = author if author.startswith('@') else f"@{author}"

        if not subtitle:
            try:
                script_tag = soup.find("script", string=re.compile(r'"username"'))
                if script_tag:
                    match = re.search(r'"username":\s*"([^"]+)"', script_tag.string)
                    if match:
                        subtitle = f"@{match.group(1)}"
            except:
                pass

        subtitle = normalize_subtitle(subtitle or "Instagram")

        # ============ EXTRACT CONTENT ============
        content = (
                get_meta_content(soup, 'og:description') or
                get_meta_content(soup, 'description', attr='name') or
                get_meta_content(soup, 'twitter:description', attr='name')
        )

        if content:
            content = re.sub(r'\d+[KM]?\s+(?:likes?|comments?|views?)', '', content, flags=re.IGNORECASE)
            content = content.strip()

        if not content or not content.strip():
            content = title

        print(f"DEBUG - FINAL: title={title[:50]}, subtitle={subtitle}, media_type={media_type}")
        print(f"DEBUG - FINAL: media_url={media_url[:100] if media_url else None}")

        return title, subtitle, media_url, content, media_type

    except Exception as e:
        print(f"ERROR in get_instagram_metadata: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None, None, None

    finally:
        # Clean up driver
        if driver:
            await quit_driver(driver)