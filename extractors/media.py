import re
from urllib.parse import urlparse
from typing import Optional
import discord

from utils.text import extract_urls_from_text
from extractors.twitter import get_twitter_metadata
from extractors.youtube import get_youtube_metadata
from extractors.instagram import get_instagram_metadata
from extractors.tiktok import get_tiktok_metadata

DEFAULT_PLACEHOLDER = "https://dummyimage.com/600x400/e0e0e0/555.png&text=No+Image"


async def extract_media_from_message(msg: discord.Message) -> str:
    """
    Extract media from a Discord message.
    Priority: attachments > platform-specific extractors > embeds > placeholder
    """
    # 1. Video attachments
    for att in msg.attachments:
        if getattr(att, "content_type", None) and att.content_type.startswith("video/"):
            return att.url

    # 2. Image attachments
    for att in msg.attachments:
        if getattr(att, "content_type", None) and att.content_type.startswith("image/"):
            return att.url

    # 3. URLs in message - use platform-specific extractors
    urls = extract_urls_from_text(msg.content or "")
    for url in urls:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Twitter/X
        if any(d in domain for d in ("twitter.com", "x.com", "fxtwitter.com", "vxtwitter.com")):
            _, _, media, _, _ = await get_twitter_metadata(url)
            if media and media != DEFAULT_PLACEHOLDER:
                return media

        # YouTube
        if "youtube.com" in domain or "youtu.be" in domain:
            _, _, media, _, _ = await get_youtube_metadata(url)
            if media and media != DEFAULT_PLACEHOLDER:
                return media

        # TikTok
        if "tiktok.com" in domain:
            _, _, media, _, _ = await get_tiktok_metadata(url)
            if media and media != DEFAULT_PLACEHOLDER:
                return media

        # Instagram
        if "instagram.com" in domain or "kkinstagram.com" in domain:
            _, _, media, _, _ = await get_instagram_metadata(url)
            if media and media != DEFAULT_PLACEHOLDER:
                return media

        # Vimeo (simple fallback)
        if "vimeo.com" in domain:
            m = re.search(r"vimeo\.com/(\d+)", url)
            if m:
                return f"https://vimeo.com/{m.group(1)}"

    # 4. Discord embeds
    for embed in msg.embeds:
        if getattr(embed, "image", None) and getattr(embed.image, "url", None):
            return embed.image.url
        if getattr(embed, "thumbnail", None) and getattr(embed.thumbnail, "url", None):
            return embed.thumbnail.url
        if getattr(embed, "video", None) and getattr(embed.video, "url", None):
            if not any(d in embed.video.url for d in ("youtube.com", "youtu.be")):
                return embed.video.url

    # 5. Fallback
    return DEFAULT_PLACEHOLDER