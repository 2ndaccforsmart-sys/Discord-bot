import re
import time
import asyncio
from scrapling.fetchers import FetcherSession, StealthyFetcher

from utils.json_utils import safe_write_json, safe_read_json
from utils.progress import make_progress_bar

AJAX_TOKEN_PATTERNS = [
    r"ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r"window\.ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r"var\s+ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r"let\s+ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r"const\s+ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r'data-token=["\']([^"\']+)["\']',
    r'"ajaxToken"\s*:\s*"([^"]+)"',
]

SEC_COOKIE_PATTERNS = [
    "ATERNOS_SEC_",
    "ATERNOS_XSRF",
    "ATERNOS CSRF",
    "XSRF-TOKEN",
]

LOGIN_PAGE_PATTERNS = ["login", "signin", "auth"]
LOGIN_SELECTORS_USER = [
    'input[name="user"]',
    'input[name="username"]',
    'input[name="email"]',
    'input[type="email"]',
    '#username',
    '#user',
    '#email',
]
LOGIN_SELECTORS_PASS = [
    'input[name="password"]',
    'input[name="pass"]',
    'input[type="password"]',
    '#password',
    '#pass',
]
LOGIN_SELECTORS_SUBMIT = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button[name="submit"]',
    'button.login',
    'button.btn-login',
    'button.btn-primary',
]


def extract_ajax_token(page_text: str) -> str | None:
    for pattern in AJAX_TOKEN_PATTERNS:
        match = re.search(pattern, page_text)
        if match:
            return match.group(1)
    return None


def extract_sec_cookie(cookies: dict) -> str | None:
    for pattern in SEC_COOKIE_PATTERNS:
        for name, value in cookies.items():
            if pattern in name:
                sec_name = name.replace(pattern, "").strip("_-")
                return f"{sec_name}:{value}" if sec_name else value
    return None


def is_login_page(url: str, text: str) -> bool:
    url_lower = url.lower() if url else ""
    text_lower = text.lower() if text else ""
    if any(p in url_lower for p in LOGIN_PAGE_PATTERNS):
        return True
    if "input[type='password']" in text or 'type="password"' in text_lower:
        return True
    return False


def aternos_login(username: str, password: str, proxy_url: str | None, state_file: str) -> tuple[dict, str]:
    if not username or not password:
        raise Exception("Missing ATERNOS_USER or ATERNOS_PASS environment variables.")

    flag_sets = [
        {"headless": True, "disable_resources": True, "block_ads": True, "network_idle": True, "solve_cloudflare": True, "timeout": 30000},
        {"headless": True, "disable_resources": False, "block_ads": False, "network_idle": True, "solve_cloudflare": True, "timeout": 45000},
        {"headless": False, "disable_resources": True, "block_ads": True, "network_idle": False, "solve_cloudflare": True, "timeout": 60000},
    ]

    last_error = None
    for attempt, flags in enumerate(flag_sets):
        try:
            fetch_args = {"url": "https://aternos.org/servers/", **flags}
            if proxy_url:
                fetch_args["proxy"] = proxy_url

            def fill_and_submit(page):
                for sel in LOGIN_SELECTORS_USER:
                    try:
                        page.fill(sel, username)
                        break
                    except Exception:
                        continue
                for sel in LOGIN_SELECTORS_PASS:
                    try:
                        page.fill(sel, password)
                        break
                    except Exception:
                        continue
                for sel in LOGIN_SELECTORS_SUBMIT:
                    try:
                        page.click(sel)
                        break
                    except Exception:
                        continue

            fetch_args["page_action"] = fill_and_submit
            print(f"StealthyFetcher login attempt {attempt + 1}/{len(flag_sets)}...")
            resp = StealthyFetcher.fetch(**fetch_args)

            cookies = {}
            if hasattr(resp, "cookies") and resp.cookies:
                for c in resp.cookies:
                    cookies[c.name] = c.value

            session_token = cookies.get("ATERNOS_SESSION")
            if session_token:
                safe_write_json(state_file, {"ATERNOS_SESSION": session_token})
                print("Session token saved.")
                return cookies, session_token
            else:
                print(f"Attempt {attempt + 1}: no ATERNOS_SESSION cookie.")
                last_error = "No session cookie after login"

        except Exception as e:
            last_error = str(e)
            print(f"Login attempt {attempt + 1} failed: {e}")
            time.sleep(2)

    raise Exception(f"All login attempts failed. Last error: {last_error}")


def validate_session(session_token: str | None, proxy_url: str | None) -> bool:
    if not session_token:
        return False
    try:
        with FetcherSession(proxy=proxy_url, verify=True) as session:
            session._curl_session.cookies.set("ATERNOS_SESSION", session_token, domain=".aternos.org")
            resp = session.get("https://aternos.org/server/")
            page_url = resp.url if hasattr(resp, "url") else ""
            page_text = resp.text if hasattr(resp, "text") else ""
            if is_login_page(page_url, page_text):
                print("Session expired.")
                return False
            print("Session valid.")
            return True
    except Exception as e:
        print(f"Session check failed: {e}")
        return False


def execute_aternos_action(action_type: str, session_token: str | None, all_cookies: dict, proxy_url: str | None) -> int:
    with FetcherSession(proxy=proxy_url, verify=True) as session:
        for name, value in all_cookies.items():
            session._curl_session.cookies.set(name, value, domain=".aternos.org")
        if session_token:
            session._curl_session.cookies.set("ATERNOS_SESSION", session_token, domain=".aternos.org")

        page = session.get("https://aternos.org/server/")
        page_text = page.text if hasattr(page, "text") else ""

        if is_login_page(page.url if hasattr(page, "url") else "", page_text):
            raise Exception("SESSION_EXPIRED: Cookie died between validation and AJAX call.")

        ajax_token = extract_ajax_token(page_text)
        sec_header_val = extract_sec_cookie(dict(session._curl_session.cookies))

        if not ajax_token:
            raise Exception("TOKEN_MISSING: Could not extract ajaxToken. Aternos may have changed their JS.")
        if not sec_header_val:
            raise Exception("SEC_MISSING: Could not extract SEC cookie. Aternos may have changed cookie names.")

        headers = {
            "X-Requested-With": "XMLHttpRequest",
            "SEC": sec_header_val,
            "Referer": "https://aternos.org/server/",
        }

        if action_type == "start":
            url = f"https://aternos.org/panel/ajax/start.php?headstart=0&access-credits=0&token={ajax_token}"
        elif action_type == "stop":
            url = f"https://aternos.org/panel/ajax/stop.php?token={ajax_token}"
        else:
            raise Exception(f"Unknown action: {action_type}")

        res = session.get(url, headers=headers)
        print(f"{action_type} response: {res.status}")
        return res.status


def execute_aternos_scrapling(
    action_type: str,
    username: str,
    password: str,
    session_token: str | None,
    state_file: str,
    proxy_url: str | None,
    update_status_sync,
) -> None:
    MAX_RETRIES = 2
    all_cookies = {}

    for attempt in range(MAX_RETRIES + 1):
        try:
            if attempt == 0:
                update_status_sync(f"Validating session...\n{make_progress_bar(20)}")
                session_valid = validate_session(session_token, proxy_url)
            else:
                session_valid = False

            if not session_valid:
                update_status_sync(f"Logging in to Aternos...\n{make_progress_bar(30)}")
                all_cookies, new_token = aternos_login(username, password, proxy_url, state_file)
                if new_token:
                    session_token = new_token
            else:
                state_data = safe_read_json(state_file)
                if state_data:
                    all_cookies["ATERNOS_SESSION"] = state_data.get("ATERNOS_SESSION", session_token)
                else:
                    all_cookies["ATERNOS_SESSION"] = session_token

            update_status_sync(f"Executing {action_type} command...\n{make_progress_bar(70)}")
            execute_aternos_action(action_type, session_token, all_cookies, proxy_url)
            update_status_sync(f"{action_type.capitalize()} command sent.\n{make_progress_bar(100)}")
            return

        except Exception as e:
            err_msg = str(e)
            if "SESSION_EXPIRED" in err_msg and attempt < MAX_RETRIES:
                print(f"Session died mid-flow, retrying... (attempt {attempt + 2})")
                session_token = None
                all_cookies = {}
                continue
            raise

    raise Exception("All retry attempts exhausted.")


async def run_aternos_action(ctx, action_type: str, status_msg, proxy_url: str | None) -> None:
    import os
    username = os.getenv("ATERNOS_USER")
    password = os.getenv("ATERNOS_PASS")
    session_token = os.getenv("ATERNOS_SESSION")
    state_file = "aternos_state.json"

    state_data = safe_read_json(state_file)
    if state_data:
        session_token = state_data.get("ATERNOS_SESSION") or session_token

    await status_msg.edit(content=f"Processing {action_type} request...")

    loop = asyncio.get_running_loop()

    def update_status_sync(message):
        asyncio.run_coroutine_threadsafe(status_msg.edit(content=message), loop)

    try:
        await asyncio.to_thread(
            execute_aternos_scrapling,
            action_type,
            username,
            password,
            session_token,
            state_file,
            proxy_url,
            update_status_sync,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        err = str(e)
        if "TOKEN_MISSING" in err or "SEC_MISSING" in err:
            await status_msg.edit(content="Aternos changed their page structure. Needs code update.")
        elif "SESSION_EXPIRED" in err:
            await status_msg.edit(content="Session expired and re-login failed. Check credentials.")
        elif "login" in err.lower():
            await status_msg.edit(content="Login failed. Check ATERNOS_USER/ATERNOS_PASS.")
        else:
            await status_msg.edit(content="Automation failed. Check logs.")
