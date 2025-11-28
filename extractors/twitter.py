import re
from typing import Optional, Dict, Tuple
from bs4 import BeautifulSoup

from utils.http import http_get
from utils.text import extract_urls_from_text
from extractors.base import get_meta_content
from utils.normalize import normalize_title, normalize_subtitle

DEFAULT_PLACEHOLDER = "https://dummyimage.com/600x400/e0e0e0/555.png&text=No+Image"


# ---------- Twitter/X utilities ----------

async def get_tweet_data(tweet_id: str) -> Optional[Dict]:
    """Fetch tweet data from fxtwitter API."""
    try:
        resp = await http_get(f"https://api.fxtwitter.com/status/{tweet_id}", timeout=5)
        if resp and resp.status_code == 200:
            data = resp.json()
            print(f"DEBUG - fxtwitter API response: {data}")  # Debug log
            if isinstance(data, dict) and "tweet" in data:
                return data.get("tweet")
    except Exception as e:
        print(f"Error fetching tweet {tweet_id}: {e}")
    return None


def extract_tweet_id(url: str) -> Optional[str]:
    """Extract tweet ID from any Twitter/X URL variant."""
    match = re.search(r"/status/(\d+)", url)
    if match:
        return match.group(1)
    return None


def is_video_url(url: str) -> bool:
    """Check if a URL points to a video file."""
    if not url:
        return False

    # Check file extension
    video_extensions = ('.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v', '.gif')
    url_lower = url.lower()
    if any(url_lower.endswith(ext) for ext in video_extensions):
        return True

    # Check for common video hosting patterns
    video_patterns = [
        r'video\.twimg\.com',
        r'/amplify_video/',
        r'/ext_tw_video/',
        r'\.mp4',
        r'\.webm',
    ]

    return any(re.search(pattern, url_lower) for pattern in video_patterns)


async def get_twitter_metadata(url: str) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract title, subtitle, media URL, content, and media type from a Twitter/X URL.
    Returns (title, subtitle, media_url, content, media_type)
    """
    try:
        tweet_id = extract_tweet_id(url)
        if not tweet_id:
            return None, None, None, None, None

        tweet_data = await get_tweet_data(tweet_id)
        if not tweet_data or not isinstance(tweet_data, dict):
            return None, None, None, None, None

        # Get the FULL tweet text (don't remove URLs for content)
        full_text = tweet_data.get("text", "")

        # Title: tweet text with URLs removed
        title = full_text
        if isinstance(title, str):
            title = re.sub(r'https?://\S+', '', title).strip()
        title = normalize_title(title or None)

        # Subtitle: author name
        subtitle = None
        author = tweet_data.get("author")
        if isinstance(author, dict):
            subtitle = author.get("name")
        subtitle = normalize_subtitle(subtitle or None)

        # Content: Keep the FULL text without normalization here
        content = full_text if full_text else None

        # Media: try multiple sources
        media_url = None
        media_type = None

        # 1. Try the media photos/videos first
        media_obj = tweet_data.get("media")
        print(f"DEBUG - media object: {media_obj}")

        if isinstance(media_obj, dict):
            # Try videos first (priority for videos)
            videos = media_obj.get("videos", [])
            if isinstance(videos, list) and len(videos) > 0:
                video = videos[0]
                if isinstance(video, dict):
                    media_url = video.get("url")
                    if media_url:
                        media_type = "video"
                        print(f"DEBUG - Found video URL: {media_url}")

            # Try photos if no video
            if not media_url:
                photos = media_obj.get("photos", [])
                if isinstance(photos, list) and len(photos) > 0:
                    photo = photos[0]
                    if isinstance(photo, dict):
                        media_url = photo.get("url")
                        if media_url:
                            media_type = "image"
                            print(f"DEBUG - Found photo URL: {media_url}")

        elif isinstance(media_obj, list):
            # Handle if media is a list
            for m in media_obj:
                if isinstance(m, dict):
                    m_type = m.get("type")
                    if m_type in ("video", "gif"):
                        media_url = m.get("url")
                        if media_url:
                            media_type = "video"
                            print(f"DEBUG - Found media from list (video): {media_url}")
                            break
                    elif m_type in ("photo", "image"):
                        media_url = m.get("url")
                        if media_url:
                            media_type = "image"
                            print(f"DEBUG - Found media from list (photo): {media_url}")
                            break

        # 2. If no media found, extract URLs from tweet text and fetch OG image
        if not media_url:
            print(f"DEBUG - No direct media, checking embedded URLs")
            tweet_text_with_urls = tweet_data.get("text", "")
            embedded_urls = extract_urls_from_text(tweet_text_with_urls)
            print(f"DEBUG - Found embedded URLs: {embedded_urls}")

            for embedded_url in embedded_urls:
                # Skip if it's the tweet URL itself
                if "/status/" in embedded_url:
                    continue

                print(f"DEBUG - Fetching OG image from: {embedded_url}")
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    resp = await http_get(embedded_url, headers=headers, timeout=10)
                    print(f"DEBUG - Response received: {resp is not None}")
                    if resp:
                        print(f"DEBUG - Response status: {resp.status_code}")
                    if resp and resp.status_code == 200:
                        soup = BeautifulSoup(resp.content, 'html.parser')
                        og_img = get_meta_content(soup, 'og:image')
                        print(f"DEBUG - og:image found: {og_img}")
                        if og_img:
                            media_url = og_img
                            media_type = "image"
                            print(f"DEBUG - Found OG image from embedded URL: {media_url}")
                            break
                    else:
                        print(f"DEBUG - Failed to fetch URL or bad status code")
                except Exception as e:
                    print(f"DEBUG - Error fetching embedded URL: {e}")
                    import traceback
                    traceback.print_exc()

        # 3. Verify media type based on URL if we have media
        if media_url and not media_type:
            media_type = "video" if is_video_url(media_url) else "image"
        elif media_url and media_type == "image" and is_video_url(media_url):
            # Double-check: if marked as image but URL is clearly video
            media_type = "video"
            print(f"DEBUG - Corrected media type to video based on URL")

        # 4. If still no media, use placeholder
        if not media_url:
            media_url = DEFAULT_PLACEHOLDER
            media_type = "image"
            print(f"DEBUG - No media found, using placeholder: {media_url}")

        print(
            f"DEBUG - Final metadata: title={title}, subtitle={subtitle}, media_url={media_url}, content_length={len(content) if content else 0}, media_type={media_type}")
        return title, subtitle, media_url, content, media_type
    except Exception as e:
        print(f"Error in get_twitter_metadata: {e}")
        import traceback
        traceback.print_exc()
        return None, None, None, None, None