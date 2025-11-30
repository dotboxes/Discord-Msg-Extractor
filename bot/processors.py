import os
import re
import asyncio
from datetime import datetime
from typing import Optional
import json
import requests
import discord

from utils.text import extract_urls_from_text
from utils.normalize import (
    normalize_title,
    normalize_subtitle,
    normalize_content,
    normalize_slug,
    strip_or_none,
)
from utils.markdown import parse_markdown_headings
from extractors.link import extract_link_metadata
from extractors.media import extract_media_from_message, DEFAULT_PLACEHOLDER

API_BASE_URL = os.getenv("API_URL", "").rstrip("/")


# ---------- Main archive processing ----------

async def process_archive(interaction: discord.Interaction, message: discord.Message):
    """Background task to process and archive a message."""
    try:
        msg = message
        raw_text = msg.content or ""
        title: Optional[str] = None
        subtitle: Optional[str] = None
        cleaned_content: Optional[str] = None
        media_url: Optional[str] = None
        media_type: str = "image"  # default media type

        urls = extract_urls_from_text(raw_text)
        content_without_urls = re.sub(r'https?://[^\s]+', '', raw_text).strip()
        is_link_only = bool(urls and not content_without_urls and not msg.attachments)

        # -----------------------------
        # Branch 1: link-only message
        # -----------------------------
        # Branch 1: link-only message
        if is_link_only:
            url = urls[0]
            meta_title, meta_subtitle, meta_media, meta_content, note = await extract_link_metadata(url)

            # Determine media type
            url_lower = url.lower()
            if any(platform in url_lower for platform in ['youtube', 'youtu.be']):
                media_type = "video"
            elif meta_media:
                from extractors.twitter import is_video_url
                media_type = "video" if is_video_url(meta_media) else "image"

            title = meta_title or "Untitled"
            subtitle = meta_subtitle
            media_url = meta_media or DEFAULT_PLACEHOLDER
            cleaned_content = meta_content or url

            if note:
                await interaction.followup.send(
                    f"⚠️ {note}",
                    ephemeral=True
                )

        # -----------------------------
        # Branch 2: text/markdown or message with links
        # -----------------------------
        else:
            md_title, md_subtitle, md_cleaned = parse_markdown_headings(raw_text)
            title = md_title or "Untitled"
            subtitle = md_subtitle
            cleaned_content = md_cleaned
            media_url = await extract_media_from_message(msg)

            # If title/content is empty and we have URLs, try link metadata
            if urls:
                meta_title, meta_subtitle, meta_media, meta_content, note = await extract_link_metadata(urls[0])
                if meta_title:
                    if not title or title == "Untitled":
                        title = meta_title
                    if not subtitle and meta_subtitle:
                        subtitle = meta_subtitle
                    if not cleaned_content and meta_content:
                        cleaned_content = meta_content
                    if not media_url or media_url == DEFAULT_PLACEHOLDER:
                        if meta_media:
                            media_url = meta_media

                if note:
                    await interaction.followup.send(
                        f"⚠️ {note}",
                        ephemeral=True
                    )

                # Determine media type from URL
                if media_url and media_url != DEFAULT_PLACEHOLDER:
                    from extractors.twitter import is_video_url
                    # Check URL patterns to determine if it's video
                    url_lower = urls[0].lower()
                    if any(platform in url_lower for platform in ['tiktok', 'youtube', 'youtu.be']):
                        media_type = "video"
                    elif 'twitter.com' in url_lower or 'x.com' in url_lower:
                        media_type = "video" if is_video_url(media_url) else "image"
                    elif 'instagram.com' in url_lower:
                        # Instagram can be either - check if media_url is video
                        media_type = "video" if is_video_url(media_url) else "image"
                    else:
                        media_type = "video" if is_video_url(media_url) else "image"

            # Fallback: if cleaned_content still empty, use raw message
            if not cleaned_content or not cleaned_content.strip():
                cleaned_content = raw_text


            # Candidate subtitle if missing
            if not subtitle:
                cleaned_for_subtitle = re.sub(r'https?://\S+', '', cleaned_content)
                cleaned_for_subtitle = re.sub(r'\s+', ' ', cleaned_for_subtitle).strip().rstrip('<>')
                subtitle = cleaned_for_subtitle[:600] if cleaned_for_subtitle else None

        # Normalize and truncate fields
        title = normalize_title(title or "Untitled")
        subtitle = normalize_subtitle(subtitle)
        cleaned_content = normalize_content(cleaned_content)
        base_slug = normalize_slug(title)

        # Determine author: handle bot messages
        author_user = msg.author
        if msg.author.bot:
            # Try to get the author from the message reference (replied-to user)
            if msg.reference and msg.reference.resolved:
                referenced_msg = msg.reference.resolved
                if isinstance(referenced_msg, discord.Message):
                    author_user = referenced_msg.author
            # Fallback to the person who archived it (interaction user)
            else:
                author_user = interaction.user

        # Store author as JSON with name and Discord ID
        # The Discord ID can be used to look up the user in your database
        author_data = {
            "name": str(author_user),
            "discord_id": str(author_user.id)
        }

        article_data = {
            "title": title,
            "subtitle": subtitle,
            "slug": base_slug,
            "content": cleaned_content or "",
            "image_url": media_url,
            "media_type": media_type,
            "author": author_data,  # Send as dict, not string
            "category": None,
            "published_date": (
                msg.created_at.isoformat() if getattr(msg, "created_at", None)
                else datetime.utcnow().isoformat()
            )
        }

        print(f"DEBUG - Article data being sent: title={title[:50]}, subtitle={subtitle[:50] if subtitle else None}, "
              f"content_length={len(cleaned_content)}, media_type={media_type}, media_url={media_url[:100] if media_url else None}")

        # POST to API
        def post_article():
            try:
                return requests.post(f"{API_BASE_URL}/api/article_import", json=article_data, timeout=10)
            except Exception as e:
                print("Error posting to API:", e)
                return None

        resp = await asyncio.to_thread(post_article)

        if resp and resp.status_code == 201:
            try:
                response_data = resp.json()
            except Exception:
                response_data = {}
            actual_slug = response_data.get("slug", base_slug)
            article_url = f"{API_BASE_URL.rstrip('/')}/article/{actual_slug}"
            await interaction.followup.send(
                f"✅ Article saved: **{title}**" +
                (f"\nSubtitle: {subtitle}" if subtitle else "") +
                f"\nLink: {article_url}\nAuthor: {author_data['name']}",
                ephemeral=True
            )
        else:
            text_preview = (resp.text[:1900] if resp is not None and hasattr(resp, "text") else "No response")
            status = resp.status_code if resp is not None else "NoResponse"
            await interaction.followup.send(
                f"⚠️ API returned {status}:\n```\n{text_preview}\n```",
                ephemeral=True
            )

    except Exception as e:
        await interaction.followup.send(
            f"⚠️ Unexpected error:\n```\n{str(e)[:1900]}\n```",
            ephemeral=True
        )
        import traceback
        traceback.print_exc()