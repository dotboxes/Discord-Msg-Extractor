import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup

from utils.http import http_get
from extractors.base import get_meta_content
from utils.normalize import normalize_title, normalize_subtitle

DEFAULT_PLACEHOLDER = "https://dummyimage.com/600x400/e0e0e0/555.png&text=No+Image"


# ---------- YouTube utilities ----------

def extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})',
        r'youtube\.com/embed/([A-Za-z0-9_-]{11})',
        r'youtube\.com/v/([A-Za-z0-9_-]{11})',
        r'youtube\.com/shorts/([A-Za-z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_youtube_thumbnail(video_id: str, quality: str = "maxresdefault") -> str:
    """
    Get YouTube thumbnail URL.
    Quality options: maxresdefault, sddefault, hqdefault, mqdefault, default
    """
    return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"


async def get_youtube_metadata(url: str) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract title, subtitle, media URL, content, and media type from a YouTube URL.
    Returns (title, subtitle, media_url, content, media_type)
    """
    try:
        video_id = extract_youtube_id(url)
        if not video_id:
            print(f"DEBUG - Could not extract YouTube video ID from: {url}")
            return None, None, None, None, None

        print(f"DEBUG - Extracted YouTube video ID: {video_id}")

        # ✅ CHANGE THIS LINE - Use embed URL instead of thumbnail
        media_url = f"https://www.youtube.com/embed/{video_id}"
        media_type = "youtube"  # Keep as YOUTUBE video
        print(f"DEBUG - YouTube embed URL: {media_url}")

        # Fetch page metadata
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = await http_get(url, headers=headers, timeout=10)

        if not resp or resp.status_code != 200:
            print(f"DEBUG - YouTube fetch failed, using embed URL anyway")
            # Return with embed URL
            return video_id, "YouTube", media_url, url, media_type

        soup = BeautifulSoup(resp.content, 'html.parser')

        # Title: Try multiple sources
        title = (
                get_meta_content(soup, 'og:title')
                or get_meta_content(soup, 'twitter:title', attr='name')
                or get_meta_content(soup, 'name', attr='name')
                or (soup.title.string.strip() if soup.title and soup.title.string else None)
        )

        # Clean up title
        if title:
            title = re.sub(r'\s*-\s*YouTube\s*$', '', title)

        title = normalize_title(title or video_id)

        # Subtitle: Channel name
        subtitle = (
                get_meta_content(soup, 'og:site_name')
                or get_meta_content(soup, 'author', attr='name')
        )

        if not subtitle:
            try:
                script_tag = soup.find("script", string=re.compile(r'"author"'))
                if script_tag:
                    match = re.search(r'"author":\s*"([^"]+)"', script_tag.string)
                    if match:
                        subtitle = match.group(1)
            except:
                pass

        subtitle = normalize_subtitle(subtitle or "YouTube")

        # Content: Description
        content = (
                get_meta_content(soup, 'og:description')
                or get_meta_content(soup, 'description', attr='name')
                or get_meta_content(soup, 'twitter:description', attr='name')
        )

        if not content or not content.strip():
            content = title

        print(f"DEBUG - YouTube: title={title}, embed={media_url}")

        return title, subtitle, media_url, content, media_type

    except Exception as e:
        print(f"Error in get_youtube_metadata: {e}")
        # ✅ Even on error, try to return embed URL if we have video_id
        video_id = extract_youtube_id(url)
        if video_id:
            return (
                video_id,
                "YouTube",
                f"https://www.youtube.com/embed/{video_id}",
                url,
                "video"
            )
        return None, None, None, None, None