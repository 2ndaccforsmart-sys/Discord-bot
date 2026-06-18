import os
import json
import time
import random
import asyncio
from pathlib import Path

ANTI_DETECT_INIT_SCRIPT = """
// Override webdriver detection
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Override chrome automation flags
window.chrome = { runtime: {} };

// Override permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

// Override plugins length to look like real browser
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Override languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Remove automation-related properties
delete navigator.__proto__.webdriver;

// Override toString to hide modifications
const originalToString = Function.prototype.toString;
Function.prototype.toString = function() {
    if (this === Function.prototype.toString) return 'function toString() { [native code] }';
    return originalToString.call(this);
};

// Mask Playwright-specific properties
if (window.__playwright) delete window.__playwright;
if (window.__pw_manual) delete window.__pw_manual;
if (window.__PW_inspect) delete window.__PW_inspect;
"""

FINGERPRINTS = [
    {"browser": "chrome", "os": "windows", "locale": "en-US", "timezone": "America/New_York"},
    {"browser": "chrome", "os": "windows", "locale": "en-US", "timezone": "America/Chicago"},
    {"browser": "chrome", "os": "windows", "locale": "en-US", "timezone": "America/Los_Angeles"},
    {"browser": "chrome", "os": "macos", "locale": "en-US", "timezone": "America/New_York"},
    {"browser": "edge", "os": "windows", "locale": "en-US", "timezone": "Europe/London"},
    {"browser": "chrome", "os": "windows", "locale": "en-GB", "timezone": "Europe/London"},
    {"browser": "chrome", "os": "windows", "locale": "en-US", "timezone": "Asia/Tokyo"},
    {"browser": "firefox", "os": "windows", "locale": "en-US", "timezone": "America/New_York"},
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

STEALTHY_IMPERSONATES = [
    "chrome131", "chrome136", "chrome142", "chrome145", "chrome146",
    "edge101", "firefox133", "firefox135",
]

COOKIE_PERSIST_PATH = "stealth_cookies.json"


def get_random_fingerprint() -> dict:
    return random.choice(FINGERPRINTS)


def get_random_user_agent() -> str:
    return random.choice(USER_AGENTS)


def get_random_impersonate() -> str:
    return random.choice(STEALTHY_IMPERSONATES)


def human_delay(min_ms: int = 500, max_ms: int = 2500):
    time.sleep(random.uniform(min_ms, max_ms) / 1000)


def save_cookies(cookies: dict, filepath: str = COOKIE_PERSIST_PATH):
    try:
        existing = {}
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                existing = json.load(f)
        existing.update(cookies)
        existing["_saved_at"] = time.time()
        with open(filepath, "w") as f:
            json.dump(existing, f)
    except Exception as e:
        print(f"Cookie save failed: {e}")


def load_cookies(filepath: str = COOKIE_PERSIST_PATH) -> dict:
    try:
        if not os.path.exists(filepath):
            return {}
        with open(filepath, "r") as f:
            data = json.load(f)
        saved_at = data.pop("_saved_at", 0)
        if time.time() - saved_at > 86400 * 3:
            print("Persisted cookies are >3 days old, discarding.")
            return {}
        return data
    except Exception:
        return {}


def clear_cookies(filepath: str = COOKIE_PERSIST_PATH):
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass


def build_stealth_page_action(login_func=None, username: str = "", password: str = ""):
    def page_action(page):
        human_delay(1000, 3000)

        try:
            page.evaluate(ANTI_DETECT_INIT_SCRIPT)
        except Exception:
            pass

        human_delay(500, 1500)

        turnstile_selectors = [
            'iframe[src*="challenges.cloudflare.com"]',
            'iframe[src*="turnstile"]',
            '#turnstile-wrapper iframe',
            '.cf-turnstile iframe',
        ]
        for sel in turnstile_selectors:
            try:
                frame = page.query_selector(sel)
                if frame:
                    print("Detected Cloudflare Turnstile, waiting for auto-solve...")
                    human_delay(5000, 10000)
                    break
            except Exception:
                continue

        challenge_indicators = [
            'Checking if the site connection is secure',
            'Verify you are human',
            'Just a moment...',
            'Performing security verification',
        ]
        try:
            body_text = page.inner_text("body") if hasattr(page, "inner_text") else ""
            for indicator in challenge_indicators:
                if indicator.lower() in body_text.lower():
                    print(f"Cloudflare challenge detected: '{indicator}', waiting...")
                    human_delay(8000, 15000)
                    break
        except Exception:
            pass

        if login_func and username and password:
            human_delay(1000, 2000)
            login_func(page, username, password)

    return page_action


def build_warmup_action():
    def page_action(page):
        human_delay(2000, 4000)
        try:
            page.evaluate("""
                window.scrollTo(0, document.body.scrollHeight / 3);
            """)
        except Exception:
            pass
        human_delay(1000, 2000)
        try:
            page.evaluate("""
                window.scrollTo(0, 0);
            """)
        except Exception:
            pass
        human_delay(500, 1000)
    return page_action


class StealthSession:
    def __init__(self, proxy_url: str | None = None):
        self.proxy_url = proxy_url
        self.fingerprint = get_random_fingerprint()
        self.cookies = load_cookies()

    def get_stealthy_fetch_args(self, url: str, **overrides) -> dict:
        fp = self.fingerprint
        args = {
            "url": url,
            "headless": True,
            "disable_resources": True,
            "block_ads": True,
            "network_idle": True,
            "solve_cloudflare": True,
            "hide_canvas": True,
            "block_webrtc": True,
            "allow_webgl": True,
            "real_chrome": False,
            "google_search": True,
            "timeout": 60000,
            "locale": fp["locale"],
            "timezone_id": fp["timezone"],
            "extra_flags": [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
                "--disable-web-security",
                "--no-sandbox",
            ],
        }
        if self.proxy_url:
            args["proxy"] = self.proxy_url
        if self.cookies:
            args["cookies"] = self.cookies
        args.update(overrides)
        return args

    def get_curl_session_args(self) -> dict:
        args = {
            "impersonate": get_random_impersonate(),
            "retries": 3,
            "retry_delay": 2,
            "follow_redirects": True,
            "verify": True,
        }
        if self.proxy_url:
            args["proxy"] = self.proxy_url
        return args

    def save_session_cookies(self, cookies: dict):
        self.cookies.update(cookies)
        save_cookies(self.cookies)
