import re
from urllib.parse import urlparse
from typing import Optional, Tuple
from bs4 import BeautifulSoup
import discord
from discord import Interaction

from utils.http import http_get
from extractors.base import get_meta_content
from extractors.youtube import get_youtube_metadata
from extractors.twitter import get_twitter_metadata
from extractors.tiktok import get_tiktok_metadata
from extractors.instagram import get_instagram_metadata
from extractors.reddit import get_reddit_metadata

from utils.normalize import normalize_title, normalize_subtitle


async def extract_link_metadata(url: str, timeout: int = 10) -> Tuple[
    Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Extract title, subtitle, media_url, content, and optional note.
    Returns: title, subtitle, media_url, content, note
    """
    note: Optional[str] = None
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # YouTube
    if "youtube.com" in domain or "youtu.be" in domain:
        title, subtitle, media_url, content, media_type = await get_youtube_metadata(url)
        if title:
            content = f"{content}\n\n{url}" if content else f"{title}\n\n{url}"
            return title, subtitle, media_url, content, note
        return None, None, None, None, note

    # Twitter/X
    if any(d in domain for d in ("twitter.com", "x.com", "fxtwitter.com", "vxtwitter.com")):
        title, subtitle, media_url, content, media_type = await get_twitter_metadata(url)
        if title:
            content = f"{content}\n\n{url}" if content else f"{title}\n\n{url}"
            return title, subtitle, media_url, content, note
        return None, None, None, None, note

    # Instagram
    if "instagram.com" in domain:
        title, subtitle, media_url, content, media_type = await get_instagram_metadata(url)
        if title:
            note = "Instagram links are not fully supported. Please verify manually."
            content = f"{content}\n\n{url}" if content else f"{title}\n\n{url}"
            return title, subtitle, media_url, content, note
        return None, None, None, None, note

    # TikTok
    #if "tiktok.com" in domain:
        title, subtitle, media_url, content, media_type = await get_tiktok_metadata(url)
        note = "TikTok links are not fully supported. Please verify manually."
        content = f"{content}\n\n{url}" if content else url
        return title, subtitle, media_url, content, note

    # Reddit
    #if "reddit.com" in domain:
        title, subtitle, media_url, content, media_type = await get_reddit_metadata(url)
        if title:
            note = "Reddit posts may contain multiple media items. Only the first item is used."
            content = f"{content}\n\n{url}" if content else f"{title}\n\n{url}"
            return title, subtitle, media_url, content, note
        return None, None, None, None, note

    # Standard HTML metadata extraction
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    resp = await http_get(url, headers=headers, timeout=timeout)
    if not resp or resp.status_code != 200:
        return None, None, None, None, note

    soup = BeautifulSoup(resp.content, 'html.parser')

    # Title
    title = get_meta_content(soup, 'og:title') or \
            get_meta_content(soup, 'twitter:title', attr='name') or \
            (soup.title.string.strip() if soup.title and soup.title.string else None)

    # Subtitle
    subtitle = get_meta_content(soup, 'og:description') or \
               get_meta_content(soup, 'description', attr='name') or \
               get_meta_content(soup, 'twitter:description', attr='name')

    # Media
    media_url = get_meta_content(soup, 'og:video') or \
                get_meta_content(soup, 'og:image') or \
                get_meta_content(soup, 'twitter:image', attr='name')

    # Extract main content
    for s in soup(["script", "style"]):
        s.decompose()

    main_content = soup.find('main') or soup.find('article') or soup.find(
        class_=re.compile(r'content|article|post', re.I))
    paras = main_content.find_all('p', limit=2) if main_content else soup.find_all('p', limit=2)

    extracted_content = ""
    if paras:
        parts = [p.get_text(separator=' ', strip=True) for p in paras if p.get_text(strip=True)]
        extracted_content = "\n\n".join(parts)

    body_content = f"{extracted_content}\n\n{url}" if extracted_content else url

    # Normalize
    title = normalize_title(title)
    subtitle = normalize_subtitle(subtitle)

    return title, subtitle, media_url, body_content, note


async def send_metadata_message(
    interaction: Interaction,
    url: str,
    timeout: int = 10,
    ephemeral: bool = True
):
    """
    Sends a single message with metadata and edits it if a note exists.
    """
    title, subtitle, media_url, content, note = await extract_link_metadata(url, timeout=timeout)

    message_content = f"**{title or 'No Title'}**"
    if subtitle:
        message_content += f"\n_{subtitle}_"
    if content:
        message_content += f"\n{content}"

    # Send initial message
    await interaction.response.send_message(message_content, ephemeral=ephemeral)
    msg = await interaction.original_response()

    # If there is a note, edit the same message
    if note:
        new_content = f"{message_content}\n\n⚠️ {note}"
        await msg.edit(content=new_content)
