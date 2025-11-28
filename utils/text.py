import re
from typing import Optional, List

def slugify(text: str, max_len: int = 1200) -> str:
    if not text:
        return "untitled"
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return s[:max_len]


def strip_or_none(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s2 = s.strip()
    return s2 if s2 else None


def extract_urls_from_text(text: str) -> List[str]:
    if not text:
        return []
    url_pattern = r'https?://[^\s<>"]+'
    return re.findall(url_pattern, text)