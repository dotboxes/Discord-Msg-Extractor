import re
import os
import hashlib
from typing import Optional, Dict, Tuple
from bs4 import BeautifulSoup

from utils.http import http_get
from utils.text import extract_urls_from_text
from extractors.base import get_meta_content
from utils.normalize import normalize_title, normalize_subtitle

DEFAULT_PLACEHOLDER = "https://dummyimage.com/600x400/e0e0e0/555.png&text=No+Image"

# Configure your video storage paths
VIDEO_STORAGE_DIR = "/path/to/public/videos"  # Change this to your actual path
VIDEO_URL_PREFIX = "/videos"  # URL path to access videos
THUMBNAIL_STORAGE_DIR = "/path/to/public/videos/thumbnails"  # Change this to your actual path
THUMBNAIL_URL_PREFIX = "/videos/thumbnails"


# ---------- Video Download utilities ----------

async def download_video(video_url: str) -> Optional[str]:
    """
    Download a video file. Returns video_path as URL, or None if failed.
    """
    try:
        os.makedirs(VIDEO_STORAGE_DIR, exist_ok=True)

        # Generate unique filename
        url_hash = hashlib.md5(video_url.encode()).hexdigest()[:12]
        extension = '.mp4'
        if video_url.lower().endswith('.webm'):
            extension = '.webm'
        elif video_url.lower().endswith('.mov'):
            extension = '.mov'

        video_filename = f"twitter_{url_hash}{extension}"
        video_filepath = os.path.join(VIDEO_STORAGE_DIR, video_filename)

        if os.path.exists(video_filepath):
            return f"{VIDEO_URL_PREFIX}/{video_filename}"

        # Download video
        print(f"Downloading video from: {video_url}")
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = await http_get(video_url, headers=headers, timeout=30)

        if not resp or resp.status_code != 200:
            print(f"Failed to download video: {resp.status_code if resp else 'No response'}")
            return None

        with open(video_filepath, 'wb') as f:
            f.write(resp.content)

        print(f"Video downloaded successfully: {video_filepath}")
        return f"{VIDEO_URL_PREFIX}/{video_filename}"

    except Exception as e:
        print(f"Error downloading video: {e}")
        import traceback
        traceback.print_exc()
        return None


# ---------- Twitter/X utilities ----------

async def get_tweet_data(tweet_id: str) -> Optional[Dict]:
    try:
        resp = await http_get(f"https://api.fxtwitter.com/status/{tweet_id}", timeout=5)
        if resp and resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "tweet" in data:
                return data.get("tweet")
    except Exception as e:
        print(f"Error fetching tweet {tweet_id}: {e}")
    return None


def extract_tweet_id(url: str) -> Optional[str]:
    match = re.search(r"/status/(\d+)", url)
    if match:
        return match.group(1)
    return None


def is_video_url(url: str) -> bool:
    if not url:
        return False

    video_extensions = ('.mp4', '.webm', '.mov', '.avi', '.mkv', '.m4v', '.gif')
    url_lower = url.lower()
    if any(url_lower.endswith(ext) for ext in video_extensions):
        return True

    video_patterns = [r'video\.twimg\.com', r'/amplify_video/', r'/ext_tw_video/', r'\.mp4', r'\.webm']
    return any(re.search(pattern, url_lower) for pattern in video_patterns)


async def get_twitter_metadata(url: str) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[str], Optional[Dict]]:
    """
    Returns (title, subtitle, media_url, content, extra_info)
    extra_info = {'media_type': 'video'|'image', 'thumbnail_url': str|None}
    """
    try:
        tweet_id = extract_tweet_id(url)
        if not tweet_id:
            return None, None, None, None, None

        tweet_data = await get_tweet_data(tweet_id)
        if not tweet_data:
            return None, None, None, None, None

        full_text = tweet_data.get("text", "")
        title = normalize_title(re.sub(r'https?://\S+', '', full_text).strip() or None)
        author = tweet_data.get("author")
        subtitle = normalize_subtitle(author.get("name") if isinstance(author, dict) else None)
        content = full_text if full_text else None

        media_url = None
        media_type = None
        thumbnail_url = None
        media_obj = tweet_data.get("media")

        # --- VIDEO first ---
        if isinstance(media_obj, dict):
            videos = media_obj.get("videos", [])
            if videos:
                remote_video_url = videos[0].get("url")
                if remote_video_url:
                    media_url, thumbnail_url = await download_video(remote_video_url)
                    media_type = "video" if media_url else None

        elif isinstance(media_obj, list):
            for m in media_obj:
                m_type = m.get("type")
                if m_type in ("video", "gif"):
                    remote_video_url = m.get("url")
                    if remote_video_url:
                        media_url, thumbnail_url = await download_video(remote_video_url)
                        media_type = "video" if media_url else None
                        break

        # --- PHOTOS fallback ---
        if not media_url:
            if isinstance(media_obj, dict):
                photos = media_obj.get("photos", [])
                if photos:
                    media_url = photos[0].get("url")
                    media_type = "image" if media_url else None
            elif isinstance(media_obj, list):
                for m in media_obj:
                    if m.get("type") in ("photo", "image"):
                        media_url = m.get("url")
                        media_type = "image" if media_url else None
                        break

        # --- Placeholder fallback ---
        if not media_url:
            media_url = DEFAULT_PLACEHOLDER
            media_type = "image"

        extra_info = {"media_type": media_type, "thumbnail_url": thumbnail_url}
        return title, subtitle, media_url, content, extra_info

    except Exception:
        return None, None, None, None, None


