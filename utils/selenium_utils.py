import asyncio
import time
import re
import json
import requests
from urllib.parse import unquote
from typing import Optional, Tuple
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException



def get_selenium_driver():
    """Create and configure a Selenium WebDriver instance."""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    driver = webdriver.Chrome(options=chrome_options)
    # Hide webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


async def create_driver():
    """Create driver in thread pool to avoid blocking."""
    return await asyncio.to_thread(get_selenium_driver)


async def quit_driver(driver):
    """Safely quit driver in thread pool."""
    try:
        await asyncio.to_thread(driver.quit)
    except Exception as e:
        print(f"DEBUG - Error closing driver: {e}")

# 1) Robust JSON extractor for SIGI_STATE / other variants
def extract_tiktok_json_driver(driver):
    """
    Try several patterns for the JSON blob TikTok embeds. Returns parsed dict or None.
    """
    html = driver.page_source

    # Try common script id
    patterns = [
        r'<script id="SIGI_STATE"[^>]*>(.*?)</script>',
        r'window\.__INIT_PROPS__\s*=\s*({.*?});',           # sometimes used
        r'window\["SIGI_STATE"\]\s*=\s*({.*?});',
        r'window\.__INIT_DATA__\s*=\s*({.*?});',
    ]

    for pat in patterns:
        m = re.search(pat, html, re.S)
        if m:
            txt = m.group(1).strip()
            # Some variants assign to a var: strip trailing semicolon
            if txt.endswith(';'):
                txt = txt[:-1]
            try:
                return json.loads(txt)
            except Exception:
                # Try to fix single quotes or JS-like structures: not ideal but sometimes needed
                try:
                    txt_fixed = txt.replace("'", '"')
                    return json.loads(txt_fixed)
                except Exception:
                    continue
    return None

# 2) Normalize and choose best media URL from parsed JSON structure
def choose_best_media_from_json(data):
    """
    Return (media_url, cover_url, media_type) where media_type in {"video","image"}.
    Tries multiple common paths.
    """
    if not data:
        return None, None, None

    # 2a: ItemModule is common
    item_module = data.get("ItemModule") or data.get("itemModule") or {}
    for item_id, info in item_module.items():
        # video paths
        video = info.get("video") or {}
        # video may have playAddr, downloadAddr, or url_list/urlList
        for k in ("playAddr", "downloadAddr"):
            if k in video and video[k]:
                url = video[k]
                # sometimes url is dict/list or has urlList
                if isinstance(url, dict):
                    # try urlList
                    for list_key in ("urlList", "url_list"):
                        if url.get(list_key):
                            candidate = url[list_key][-1]  # take last = highest res
                            return candidate, video.get("cover") or None, "video"
                    # otherwise look for 'uri' or 'url'
                    if url.get("url"):
                        return url["url"], video.get("cover") or None, "video"
                elif isinstance(url, list):
                    return url[-1], video.get("cover") or None, "video"
                elif isinstance(url, str):
                    return url, video.get("cover") or None, "video"

        # older style: video.playAddr.url_list or video.playAddr.urlList
        play = video.get("playAddr") or {}
        if isinstance(play, dict):
            for list_key in ("urlList","url_list"):
                if play.get(list_key):
                    return play[list_key][-1], video.get("cover") or None, "video"

        # image posts
        imgpost = info.get("imagePost") or info.get("images") or {}
        if imgpost:
            images = imgpost.get("images") or []
            if images:
                # images[0] might have imageURL, urlList, or a dict
                first = images[0]
                if isinstance(first, dict):
                    for key in ("imageURL","url","urlList","url_list"):
                        if first.get(key):
                            val = first[key]
                            if isinstance(val, list):
                                return val[-1], val[-1], "image"
                            return val, val, "image"
                elif isinstance(first, str):
                    return first, first, "image"

    # 2b: fallback to other common keys
    # Sometimes the JSON has "ItemList"/"media" etc. Try scanning for any http(s) URLs ending in .mp4/.jpeg
    whole = json.dumps(data)
    candidates = re.findall(r'https?://[^\s"\']+\.(?:mp4|m3u8|jpeg|jpg|png)', whole)
    if candidates:
        # prefer mp4
        for c in candidates:
            if c.endswith(".mp4"):
                return c, None, "video"
        return candidates[0], candidates[0], "image"

    return None, None, None

# 3) Helper: export cookies from selenium into requests.Session
def session_from_selenium(driver):
    s = requests.Session()
    # set sensible headers
    s.headers.update({
        "User-Agent": driver.execute_script("return navigator.userAgent") or "Mozilla/5.0",
        "Referer": "https://www.tiktok.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    for c in driver.get_cookies():
        s.cookies.set(c['name'], c['value'], domain=c.get('domain'))
    return s

# 4) Try to request the URL with session; follow redirects and return final URL and status
def fetch_url_with_session(session, url, method="head", timeout=8):
    try:
        # unquote sometimes helps with %7e issues
        url = unquote(url)
        if method == "head":
            r = session.head(url, allow_redirects=True, timeout=timeout)
        else:
            r = session.get(url, allow_redirects=True, timeout=timeout, stream=True)
        return r.status_code, r.url, r
    except Exception as e:
        return None, None, None

# 5) Rewriting common-sign host -> sign host heuristic
def rewrite_common_sign(url):
    if not url:
        return url
    # replace the common-sign host with a sign host that often works
    url = re.sub(r'p16-common-sign\.tiktokcdn-us\.com', 'p16-sign.tiktokcdn.com', url)
    url = re.sub(r'p16-common\.tiktokcdn\.com', 'p16-sign.tiktokcdn.com', url)
    # try removing tplv or replacing ~ encodings
    url = url.replace('%7e', '~')
    # sometimes swap region suffixes
    return url

# 6) High-level helper to get a usable media URL
def get_usable_tiktok_media_url(driver):
    # 1) parse JSON
    data = extract_tiktok_json_driver(driver)
    media_url, cover, mtype = choose_best_media_from_json(data)
    print(f"DEBUG - JSON choose: {media_url} ({mtype})")

    s = session_from_selenium(driver)

    # If JSON gave a URL, attempt to HEAD it using session cookies
    if media_url:
        status, final, resp = fetch_url_with_session(s, media_url, method="head")
        print(f"DEBUG - HEAD {media_url} -> status={status} final={final}")
        if status and status < 400:
            return final or media_url, mtype

        # try rewriting host if access denied
        rewritten = rewrite_common_sign(media_url)
        if rewritten != media_url:
            status, final, resp = fetch_url_with_session(s, rewritten, method="head")
            print(f"DEBUG - HEAD rewritten {rewritten} -> status={status} final={final}")
            if status and status < 400:
                return final or rewritten, mtype

    # 2) Fallback to DOM method you already have (video tag / poster / img)
    try:
        from selenium.webdriver.common.by import By
        videos = driver.find_elements(By.TAG_NAME, "video")
        for v in videos:
            src = v.get_attribute("src")
            poster = v.get_attribute("poster")
            if src:
                status, final, _ = fetch_url_with_session(s, src, method="head")
                if status and status < 400:
                    return final or src, "video"
                # try rewrite
                rsrc = rewrite_common_sign(src)
                status, final, _ = fetch_url_with_session(s, rsrc, method="head")
                if status and status < 400:
                    return final or rsrc, "video"
            if poster:
                status, final, _ = fetch_url_with_session(s, poster, method="head")
                if status and status < 400:
                    return final or poster, "video"

        imgs = driver.find_elements(By.TAG_NAME, "img")
        for img in imgs:
            src = img.get_attribute("src")
            if src:
                status, final, _ = fetch_url_with_session(s, src, method="head")
                if status and status < 400:
                    return final or src, "image"
                rsrc = rewrite_common_sign(src)
                status, final, _ = fetch_url_with_session(s, rsrc, method="head")
                if status and status < 400:
                    return final or rsrc, "image"
    except Exception as e:
        print(f"DEBUG - DOM fallback error: {e}")

    return None, None

def load_instagram_page_sync(driver, url: str) -> str:
    """
    Load Instagram page and wait for content to appear.
    Returns page source.
    """
    driver.get(url)

    # Try multiple selectors - Instagram's structure varies
    selectors_to_try = [
        (By.CSS_SELECTOR, "img[srcset]"),
        (By.TAG_NAME, "video"),
        (By.TAG_NAME, "article"),
        (By.CSS_SELECTOR, "main"),
        (By.CSS_SELECTOR, "[role='main']"),
    ]

    for selector_type, selector_value in selectors_to_try:
        try:
            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((selector_type, selector_value))
            )
            print(f"DEBUG - Found element with selector: {selector_value}")
            # Short wait for images to load after element is found
            time.sleep(0.5)
            return driver.page_source
        except TimeoutException:
            continue

    print(f"DEBUG - No expected elements found, proceeding anyway")
    return driver.page_source


async def load_instagram_page(driver, url: str) -> str:
    """Async wrapper for loading Instagram page."""
    return await asyncio.to_thread(load_instagram_page_sync, driver, url)


def find_video_sync(driver) -> Tuple[Optional[str], Optional[str]]:
    """
    Find video element in the page.
    Returns (video_url, media_type) or (None, None).
    """
    try:
        video_elements = driver.find_elements(By.TAG_NAME, "video")
        print(f"DEBUG - Found {len(video_elements)} video elements")
        if video_elements:
            for video in video_elements:
                src = video.get_attribute("src")
                if src and src.startswith("http"):
                    print(f"DEBUG - Found video element: {src[:100]}")
                    return src, "video"
                # Try poster attribute as fallback
                poster = video.get_attribute("poster")
                if poster and poster.startswith("http"):
                    print(f"DEBUG - Found video poster: {poster[:100]}")
                    return poster, "video"
    except Exception as e:
        print(f"DEBUG - Error finding video: {e}")
    return None, None


def find_image_sync(driver) -> Tuple[Optional[str], Optional[str]]:
    """
    Find high-resolution image in the page.
    Returns (image_url, media_type) or (None, None).
    """
    try:
        # Look for all img elements
        img_elements = driver.find_elements(By.TAG_NAME, "img")
        print(f"DEBUG - Found {len(img_elements)} img elements")

        best_img = None
        max_size = 0

        for img in img_elements:
            src = img.get_attribute("src")
            srcset = img.get_attribute("srcset")

            if not src or not src.startswith("http"):
                continue

            # Skip profile pictures, icons, and small images
            if any(skip in src for skip in ["profile_pic", "s150x150", "44x44", "instagram_logo"]):
                continue

            print(f"DEBUG - Checking image: {src[:100]}")

            # If srcset is available, parse for highest resolution
            if srcset:
                urls = []
                for part in srcset.split(','):
                    url_match = re.match(r'\s*(https?://[^\s]+)', part.strip())
                    if url_match:
                        urls.append(url_match.group(1))
                if urls:
                    # Get the last URL (usually highest res)
                    src = urls[-1]
                    print(f"DEBUG - Using srcset URL: {src[:100]}")

            # Prefer images without crop parameters
            if "s640x640" not in src:
                print(f"DEBUG - Found full-size image: {src[:150]}")
                return src, "image"

            # Track largest cropped image as fallback
            try:
                width = img.get_attribute("naturalWidth")
                height = img.get_attribute("naturalHeight")
                if width and height:
                    size = int(width) * int(height)
                    if size > max_size:
                        max_size = size
                        best_img = src
            except:
                if not best_img:
                    best_img = src

        if best_img:
            print(f"DEBUG - Using best available image: {best_img[:150]}")
            return best_img, "image"

    except Exception as e:
        print(f"DEBUG - Error finding image: {e}")
        import traceback
        traceback.print_exc()
    return None, None


async def extract_media_from_selenium(driver, is_reel=False):
    """
    Extract media URL and type from Instagram page using Selenium.

    Args:
        driver: Selenium WebDriver instance
        is_reel: Boolean indicating if this is a reel URL

    Returns:
        Tuple of (media_url, media_type)
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        # Give page time to load
        await asyncio.sleep(2)

        media_url = None
        media_type = "video" if is_reel else "image"

        # Try different selectors based on content type
        if is_reel:
            print(f"DEBUG - Looking for reel video element")

            # Reel-specific selectors (try multiple)
            video_selectors = [
                'video[playsinline]',
                'video.x1lliihq',  # Common Instagram video class
                'video',
                'div[role="presentation"] video',
                'article video',
            ]

            for selector in video_selectors:
                try:
                    video_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"DEBUG - Found {len(video_elements)} elements with selector: {selector}")

                    for video in video_elements:
                        src = video.get_attribute('src')
                        if src and ('instagram' in src or src.startswith('blob:')):
                            print(f"DEBUG - Found video src: {src[:100]}")

                            # If it's a blob URL, try to get the actual source
                            if src.startswith('blob:'):
                                # Try to find the video URL in the page source or network
                                # This is challenging with blob URLs - may need video thumbnail instead
                                print(f"DEBUG - Video is blob URL, trying poster attribute")
                                poster = video.get_attribute('poster')
                                if poster:
                                    print(f"DEBUG - Found poster: {poster[:100]}")
                                    media_url = poster
                                    # Still mark as video type
                                    media_type = "video"
                                    break
                            else:
                                media_url = src
                                media_type = "video"
                                break

                    if media_url:
                        break

                except Exception as e:
                    print(f"DEBUG - Error with selector {selector}: {e}")
                    continue

            # If still no video URL, try to get poster/thumbnail
            if not media_url:
                print(f"DEBUG - No direct video URL, looking for poster/thumbnail")
                try:
                    video_element = driver.find_element(By.CSS_SELECTOR, 'video')
                    poster = video_element.get_attribute('poster')
                    # Check if poster URL looks like a high-quality image (not thumbnail)
                    if poster and 'thumbnail' not in poster.lower() and 's150x150' not in poster and 's320x320' not in poster:
                        print(f"DEBUG - Using video poster: {poster[:100]}")
                        media_url = poster
                        media_type = "video"
                    else:
                        print(f"DEBUG - Skipping low-quality poster image")
                except:
                    pass
        else:
            # Regular post - look for images
            print(f"DEBUG - Looking for post image element")

            image_selectors = [
                'article img[srcset]',
                'div._aagv img',
                'article img',
                'img[alt]',
            ]

            for selector in image_selectors:
                try:
                    images = driver.find_elements(By.CSS_SELECTOR, selector)
                    print(f"DEBUG - Found {len(images)} images with selector: {selector}")

                    for img in images:
                        src = img.get_attribute('src')
                        srcset = img.get_attribute('srcset')

                        if srcset:
                            # Parse srcset to get highest resolution
                            urls = re.findall(r'(https://[^\s]+)', srcset)
                            if urls:
                                src = max(urls, key=len)

                        if src and 'instagram' in src:
                            print(f"DEBUG - Found image src: {src[:100]}")
                            media_url = src
                            media_type = "image"
                            break

                    if media_url:
                        break

                except Exception as e:
                    print(f"DEBUG - Error with selector {selector}: {e}")
                    continue

            # Also check for video in posts
            if not media_url:
                try:
                    video = driver.find_element(By.CSS_SELECTOR, 'video')
                    src = video.get_attribute('src')
                    if src:
                        print(f"DEBUG - Found video in post: {src[:100]}")
                        media_url = src
                        media_type = "video"
                except:
                    pass

        return media_url, media_type

    except Exception as e:
        print(f"ERROR in extract_media_from_selenium: {e}")
        import traceback
        traceback.print_exc()
        return None, "video" if is_reel else "image"


def load_tiktok_page_sync(driver, url: str) -> str:
    """
    Load TikTok page and wait for content to appear.
    Returns page source.
    """
    driver.get(url)

    # Try multiple selectors for TikTok's structure
    selectors_to_try = [
        (By.TAG_NAME, "video"),
        (By.CSS_SELECTOR, "[data-e2e='browse-video']"),
        (By.CSS_SELECTOR, "img[alt]"),
        (By.CSS_SELECTOR, "main"),
        (By.ID, "main-content-video_detail"),
    ]

    for selector_type, selector_value in selectors_to_try:
        try:
            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((selector_type, selector_value))
            )
            print(f"DEBUG - Found TikTok element with selector: {selector_value}")
            time.sleep(0.5)
            return driver.page_source
        except TimeoutException:
            continue

    print(f"DEBUG - No expected TikTok elements found, proceeding anyway")
    return driver.page_source


async def load_tiktok_page(driver, url: str) -> str:
    """Async wrapper for loading TikTok page."""
    return await asyncio.to_thread(load_tiktok_page_sync, driver, url)


def extract_tiktok_json_media(driver):
    """
    Extract video or image URL directly from TikTok's JSON in <script id="SIGI_STATE">.
    Returns (media_url, cover_url)
    """
    try:
        html = driver.page_source
        match = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', html, re.S)
        if not match:
            print("DEBUG - No SIGI_STATE JSON found")
            return None, None

        data = json.loads(match.group(1))
        item_module = data.get("ItemModule", {})
        if not item_module:
            print("DEBUG - No ItemModule found in SIGI_STATE")
            return None, None

        for item_id, info in item_module.items():
            video_data = info.get("video", {})
            image_post = info.get("imagePost", {})

            # Handle video posts
            if "playAddr" in video_data:
                url = video_data["playAddr"]
                cover = video_data.get("cover", "")
                print(f"DEBUG - Found TikTok video URL: {url[:100]}")
                return url, cover

            # Handle photo mode / image posts
            if "images" in image_post:
                images = image_post.get("images", [])
                if images:
                    url = images[0].get("imageURL", "")
                    print(f"DEBUG - Found TikTok image URL: {url[:100]}")
                    return url, url

        print("DEBUG - No usable video or image data found in JSON")
        return None, None

    except Exception as e:
        print(f"DEBUG - Error parsing SIGI_STATE: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def find_tiktok_media_sync(driver) -> Tuple[Optional[str], str, Optional[str]]:
    """
    Find video and cover image in TikTok page.
    Returns (video_url, media_type, cover_url).
    """
    video_url = None
    cover_url = None

    try:
        # Look for video elements
        video_elements = driver.find_elements(By.TAG_NAME, "video")
        print(f"DEBUG - Found {len(video_elements)} video elements")

        for video in video_elements:
            src = video.get_attribute("src")
            if src and src.startswith("http"):
                print(f"DEBUG - Found TikTok video: {src[:100]}")
                video_url = src

            # Get poster/cover image
            poster = video.get_attribute("poster")
            if poster and poster.startswith("http"):
                print(f"DEBUG - Found TikTok cover: {poster[:100]}")
                cover_url = poster

            if video_url:
                break

        # If no video src, try to find cover images
        if not cover_url:
            img_elements = driver.find_elements(By.TAG_NAME, "img")
            print(f"DEBUG - Found {len(img_elements)} img elements")

            for img in img_elements:
                src = img.get_attribute("src")
                alt = img.get_attribute("alt")

                if not src or not src.startswith("http"):
                    continue

                # Skip TikTok logo and small icons
                if any(skip in src.lower() for skip in ["logo", "icon", "avatar"]):
                    continue

                # Look for video thumbnails
                if "tiktokcdn" in src and any(hint in src for hint in ["tos-", "video"]):
                    print(f"DEBUG - Found TikTok thumbnail: {src[:100]}")
                    cover_url = src
                    break

        # Prefer video URL, but return cover if available
        if video_url:
            return video_url, "video", cover_url
        elif cover_url:
            return cover_url, "video", cover_url

    except Exception as e:
        print(f"DEBUG - Error finding TikTok media: {e}")
        import traceback
        traceback.print_exc()

    return None, "video", None


async def extract_tiktok_media(driver) -> Tuple[Optional[str], str]:
    """
    Extract media URL and type from a TikTok page using Selenium.
    Tries JSON extraction, cookie-authenticated requests, and DOM fallbacks.
    Returns (media_url, media_type).
    """
    print("DEBUG - Starting TikTok media extraction with Selenium")

    # Use the new robust unified helper (runs in thread to avoid blocking)
    media_url, media_type = await asyncio.to_thread(get_usable_tiktok_media_url, driver)

    if media_url:
        print(f"DEBUG - ✅ Final usable TikTok media: {media_url} ({media_type})")
        return media_url, media_type

    # As last resort, fallback to your original DOM-based method
    print("DEBUG - Falling back to legacy DOM TikTok extractor")
    media_url, media_type, _ = await asyncio.to_thread(find_tiktok_media_sync, driver)
    if media_url:
        print(f"DEBUG - ✅ Legacy fallback found: {media_url} ({media_type})")
        return media_url, media_type

    print("DEBUG - ❌ No usable TikTok media found")
    return None, "video"
