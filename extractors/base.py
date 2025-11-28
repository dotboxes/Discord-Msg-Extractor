from bs4 import BeautifulSoup
from typing import Optional

def get_meta_content(soup: BeautifulSoup, prop: str, attr: str = "property") -> Optional[str]:
    tag = soup.find('meta', attrs={attr: prop})
    if tag and tag.get('content'):
        return tag.get('content').strip()
    return None

