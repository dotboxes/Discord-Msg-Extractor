# utils/normalize.py
import re

# --- Configurable limits ---
MAX_TITLE_LEN = 255
MAX_SUBTITLE_LEN = 600
MAX_CONTENT_LEN = 2000
MAX_SLUG_LEN = 1200

# --- Core truncation helpers ---

def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Safely truncate text to a maximum length."""
    if not text:
        return text
    if len(text) > max_length:
        return text[:max_length - len(suffix)] + suffix
    return text

def clean_whitespace(text: str) -> str:
    """Collapse multiple spaces/newlines and strip whitespace."""
    if not text:
        return text
    # Replace multiple spaces (but NOT newlines) with single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Replace 3+ newlines with just 2 (preserve paragraph breaks)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def clean_whitespace_inline(text: str) -> str:
    """For titles/subtitles: collapse ALL whitespace including newlines."""
    if not text:
        return text
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def strip_or_none(s: str):
    """Strip text and convert empty strings to None."""
    if s is None:
        return None
    s = s.strip()
    return s if s else None

# --- Normalization pipelines ---

def normalize_title(title: str) -> str:
    """Apply length and whitespace normalization to titles."""
    title = clean_whitespace_inline(title)  # Use inline version for titles
    return truncate_text(title, MAX_TITLE_LEN)

def normalize_subtitle(subtitle: str) -> str:
    """Apply length and whitespace normalization to subtitles."""
    subtitle = clean_whitespace_inline(subtitle)  # Use inline version for subtitles
    return truncate_text(subtitle, MAX_SUBTITLE_LEN)

def normalize_content(content: str) -> str:
    """Apply consistent truncation for article content, preserving newlines."""
    content = clean_whitespace(content)  # Preserves newlines!
    return truncate_text(content, MAX_CONTENT_LEN)

def normalize_slug(slug: str) -> str:
    """Limit slug length and clean invalid chars."""
    slug = clean_whitespace_inline(slug)
    slug = re.sub(r'[^a-zA-Z0-9-_]+', '-', slug)
    return truncate_text(slug.lower(), MAX_SLUG_LEN)
