import asyncio
import requests
from typing import Optional

def blocking_get(url: str, headers: dict = None, timeout: int = 10) -> requests.Response:
    return requests.get(url, headers=headers or {}, timeout=timeout)


async def http_get(url: str, headers: dict = None, timeout: int = 10) -> Optional[requests.Response]:
    try:
        resp = await asyncio.to_thread(blocking_get, url, headers or {}, timeout)
        return resp
    except Exception as e:
        print(f"HTTP GET error for {url}: {e}")
        return None