import re
from typing import Tuple, Optional


# ---------- Markdown heading parsing ----------

def parse_markdown_headings(content: str) -> Tuple[str, Optional[str], str]:
    """
    Extract title and subtitle from markdown headings, remove heading markers and all Discord formatting from content.
    Returns (title, subtitle, cleaned_content)

    Handles Discord markdown:
    - Headings: #, ##, ###
    - Subtext: -#
    - Masked links: [text](url)
    - Bold: **text** or __text__
    - Italic: *text* or _text_
    - Underline: __text__
    - Strikethrough: ~~text~~
    - Spoiler: ||text||
    - Code: `text`
    - Code blocks: ```text```
    - Block quotes: > or >>>
    - Combined formatting
    """
    if not content:
        return "Untitled", None, ""

    lines = content.splitlines()
    headings = []

    for i, line in enumerate(lines):
        # Match headings (# to ###)
        m = re.match(r'^(#{1,3})\s+(.+)$', line.strip())
        if m:
            lvl = len(m.group(1))
            txt = m.group(2).strip()
            # Remove all Discord markdown formatting from heading
            txt = remove_discord_formatting(txt)
            headings.append((lvl, txt, i))

    title = None
    subtitle = None
    if headings:
        headings.sort(key=lambda x: x[0])
        title = headings[0][1]  # ← REMOVED [:255] truncation
        if len(headings) > 1 and headings[1][0] != headings[0][0]:
            subtitle = headings[1][1]  # ← REMOVED [:255] truncation

    # Remove headings and subtext lines from content
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip headings (# to ###)
        if re.match(r'^#{1,3}\s+', stripped):
            continue
        # Skip subtext lines (-#)
        if re.match(r'^-#\s+', stripped):
            continue
        cleaned_lines.append(line)

    cleaned_content = "\n".join(cleaned_lines).strip()

    return title or "Untitled", subtitle, cleaned_content


def remove_discord_formatting(text: str) -> str:
    """
    Remove all Discord markdown formatting from text while preserving the actual content.

    Handles:
    - Masked links: [text](url)
    - Bold: **text** or __text__ (when used for bold)
    - Italic: *text* or _text_
    - Strikethrough: ~~text~~
    - Underline: __text__ (Discord-specific)
    - Spoiler: ||text||
    - Code: `text`
    - Code blocks: ```text``` or ```lang\ntext```
    - Block quotes: > or >>>
    - Combined formatting
    """
    if not text:
        return text

    # Remove code blocks first (```lang\ncode``` or ```code```)
    text = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).replace('```', '').strip(), text)

    # Remove inline code (`code`)
    text = re.sub(r'`([^`]+?)`', r'\1', text)

    # Remove spoilers (||text||)
    text = re.sub(r'\|\|(.+?)\|\|', r'\1', text, flags=re.DOTALL)

    # Remove strikethrough (~~text~~)
    text = re.sub(r'~~(.+?)~~', r'\1', text, flags=re.DOTALL)

    # Remove block quotes (> or >>> at line start)
    text = re.sub(r'^>>>?\s*', '', text, flags=re.MULTILINE)

    # Remove masked links [text](url) - keep the text, remove the URL
    text = re.sub(r'\[([^\]]+?)\]\([^\)]+?\)', r'\1', text)

    # Multiple passes to handle all bold/italic/underline formatting
    # This ensures we catch all instances even with emojis and special characters
    max_iterations = 5
    for _ in range(max_iterations):
        original = text

        # Remove ***text*** (bold + italic)
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text, flags=re.DOTALL)
        text = re.sub(r'___(.+?)___', r'\1', text, flags=re.DOTALL)

        # Remove **text** (bold) - use DOTALL to match across any characters including emojis
        text = re.sub(r'\*\*([^\*]+?)\*\*', r'\1', text, flags=re.DOTALL)

        # Remove __text__ (underline/bold in Discord)
        text = re.sub(r'__([^_]+?)__', r'\1', text, flags=re.DOTALL)

        # Remove *text* (italic) - single asterisks
        text = re.sub(r'(?<!\*)\*([^\*]+?)\*(?!\*)', r'\1', text, flags=re.DOTALL)

        # Remove _text_ (italic) - single underscores
        text = re.sub(r'(?<!_)_([^_]+?)_(?!_)', r'\1', text, flags=re.DOTALL)

        # If nothing changed, we're done
        if original == text:
            break

    # Clean up any remaining escape characters
    text = re.sub(r'\\([*_~`|>\\[\]])', r'\1', text)

    return text.strip()