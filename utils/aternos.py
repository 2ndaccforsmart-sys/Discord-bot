import os
import re
import time
import random
import logging
import asyncio
import traceback
from scrapling.fetchers import FetcherSession, StealthyFetcher

from utils.json_utils import safe_write_json, safe_read_json
from utils.progress import make_progress_bar
from utils.config import ATERNOS_MAX_RETRIES
from utils.stealth import (
    StealthSession, build_stealth_page_action,
    human_delay, get_random_impersonate, clear_cookies,
    COOKIE_PERSIST_PATH,
)

log = logging.getLogger("bot.aternos")

AJAX_TOKEN_PATTERNS = [
    r"ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r"window\.ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r"var\s+ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r"let\s+ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r"const\s+ajaxToken\s*=\s*['\"]([^'\"]+)['\"]",
    r'data-token=["\']([^"\']+)["\']',
    r'"ajaxToken"\s*:\s*"([^"]+)"',
    r"token\s*[:=]\s*['\"]([^'\"]{20,})['\"]",
]

SEC_COOKIE_PATTERNS = [
    "ATERNOS_SEC_",
    "ATERNOS_XSRF",
    "ATERNOS CSRF",
    "XSRF-TOKEN",
    "SEC_",
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

CF_CHALLENGE_MARKERS = [
    "checking if the site connection is secure",
    "verify you are human",
    "just a moment",
    "performing security verification",
    "enable javascript and cookies to continue",
    "cf-challenge",
    "challenge-platform",
]


def extract_ajax_token(page_text: str) -> str | None:
    for pattern in AJAX_TOKEN_PATTERNS:
        match = re.search(pattern, page_text)
        if match:
            token = match.group(1)
            if len(token) >= 10:
                return token
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


def is_cloudflare_challenge(url: str, text: str) -> bool:
    text_lower = text.lower() if text else ""
    url_lower = url.lower() if url else ""
    for marker in CF_CHALLENGE_MARKERS:
        if marker in text_lower or marker in url_lower:
            return True
    return False


def _fill_login_form(page, username: str, password: str):
    human_delay(800, 1500)

    for sel in LOGIN_SELECTORS_USER:
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                human_delay(200, 500)
                page.fill(sel, "")
                for char in username:
                    page.type(sel, char, delay=random.randint(30, 80))
                    human_delay(10, 30)
                break
        except Exception:
            continue

    human_delay(300, 700)

    for sel in LOGIN_SELECTORS_PASS:
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                human_delay(200, 500)
                page.fill(sel, "")
                for char in password:
                    page.type(sel, char, delay=random.randint(30, 80))
                    human_delay(10, 30)
                break
        except Exception:
            continue

    human_delay(500, 1200)

    for sel in LOGIN_SELECTORS_SUBMIT:
        try:
            el = page.query_selector(sel)
            if el:
                el.click()
                break
        except Exception:
            continue


def aternos_login(username: str, password: str, proxy_url: str | None, state_file: str) -> tuple[dict, str]:
    if not username or not password:
        raise Exception("Missing ATERNOS_USER or ATERNOS_PASS environment variables.")

    stealth = StealthSession(proxy_url=proxy_url)
    max_retries = ATERNOS_MAX_RETRIES
    last_error = None

    for attempt in range(max_retries):
        try:
            fp = stealth.fingerprint
            page_action = build_stealth_page_action(
                login_func=_fill_login_form,
                username=username,
                password=password,
            )

            fetch_args = stealth.get_stealthy_fetch_args(
                url="https://aternos.org/servers/",
                page_action=page_action,
                wait=random.randint(3000, 6000),
            )

            log.info("Stealth login attempt %d/%d (fingerprint: %s/%s)", attempt + 1, max_retries, fp['browser'], fp['os'])
            resp = StealthyFetcher.fetch(**fetch_args)

            page_url = resp.url if hasattr(resp, "url") else ""
            page_text = resp.text if hasattr(resp, "text") else ""

            if is_cloudflare_challenge(page_url, page_text):
                log.warning("Attempt %d: Cloudflare challenge still active. Retrying...", attempt + 1)
                human_delay(5000, 10000)
                last_error = "Cloudflare challenge not solved"
                continue

            cookies = {}
            if hasattr(resp, "cookies") and resp.cookies:
                for c in resp.cookies:
                    cookies[c.name] = c.value

            if not cookies:
                try:
                    cookie_header = resp.headers.get("set-cookie", "") if hasattr(resp, "headers") else ""
                    if cookie_header:
                        for part in cookie_header.split(","):
                            if "=" in part:
                                name, value = part.split("=", 1)
                                cookies[name.strip()] = value.split(";")[0].strip()
                except Exception:
                    pass

            session_token = cookies.get("ATERNOS_SESSION")
            if session_token:
                safe_write_json(state_file, {"ATERNOS_SESSION": session_token})
                stealth.save_session_cookies(cookies)
                log.info("Login successful on attempt %d. Session token saved.", attempt + 1)
                return cookies, session_token
            else:
                log.warning("Attempt %d: no ATERNOS_SESSION cookie. Page URL: %s", attempt + 1, page_url)
                last_error = f"No session cookie after login (URL: {page_url})"

                if is_login_page(page_url, page_text):
                    log.warning("Still on login page. Cloudflare may have blocked the attempt.")
                    last_error = "Blocked by Cloudflare or invalid credentials"

        except Exception as e:
            last_error = str(e)
            log.error("Login attempt %d failed: %s", attempt + 1, e)

        backoff = min(30, (2 ** attempt) * 2 + random.uniform(0, 3))
        log.info("Backing off %.1fs before next attempt...", backoff)
        time.sleep(backoff)

        if attempt < max_retries - 1:
            clear_cookies()
            stealth = StealthSession(proxy_url=proxy_url)

    raise Exception(f"All {max_retries} login attempts failed. Last error: {last_error}")


def validate_session(session_token: str | None, proxy_url: str | None) -> bool:
    if not session_token:
        return False

    for attempt in range(3):
        try:
            impersonation = get_random_impersonate()
            with FetcherSession(
                proxy=proxy_url,
                impersonate=impersonation,
                retries=2,
                retry_delay=2,
                verify=True,
            ) as session:
                session._curl_session.cookies.set("ATERNOS_SESSION", session_token, domain=".aternos.org")
                resp = session.get("https://aternos.org/server/")
                page_url = resp.url if hasattr(resp, "url") else ""
                page_text = resp.text if hasattr(resp, "text") else ""

                if is_cloudflare_challenge(page_url, page_text):
                    log.warning("Session validation attempt %d: Cloudflare challenge.", attempt + 1)
                    time.sleep(random.uniform(2, 5))
                    continue

                if is_login_page(page_url, page_text):
                    log.info("Session expired.")
                    return False

                log.info("Session valid.")
                return True
        except Exception as e:
            log.error("Session check attempt %d failed: %s", attempt + 1, e)
            time.sleep(random.uniform(1, 3))

    return False


def execute_aternos_action(action_type: str, session_token: str | None, all_cookies: dict, proxy_url: str | None) -> int:
    for attempt in range(3):
        try:
            impersonation = get_random_impersonate()
            with FetcherSession(
                proxy=proxy_url,
                impersonate=impersonation,
                retries=2,
                retry_delay=2,
                verify=True,
            ) as session:
                for name, value in all_cookies.items():
                    session._curl_session.cookies.set(name, value, domain=".aternos.org")
                if session_token:
                    session._curl_session.cookies.set("ATERNOS_SESSION", session_token, domain=".aternos.org")

                human_delay(500, 1500)

                page = session.get("https://aternos.org/server/")
                page_text = page.text if hasattr(page, "text") else ""
                page_url = page.url if hasattr(page, "url") else ""

                if is_cloudflare_challenge(page_url, page_text):
                    log.warning("AJAX attempt %d: Cloudflare challenge on server page.", attempt + 1)
                    time.sleep(random.uniform(3, 7))
                    continue

                if is_login_page(page_url, page_text):
                    raise Exception("SESSION_EXPIRED: Cookie died between validation and AJAX call.")

                ajax_token = extract_ajax_token(page_text)
                sec_header_val = extract_sec_cookie(dict(session._curl_session.cookies))

                if not ajax_token:
                    for extra_wait in [3, 5, 8]:
                        log.info("No ajaxToken found, waiting %ds for JS execution...", extra_wait)
                        time.sleep(extra_wait)
                        page2 = session.get("https://aternos.org/server/")
                        page_text2 = page2.text if hasattr(page2, "text") else ""
                        ajax_token = extract_ajax_token(page_text2)
                        if ajax_token:
                            page_text = page_text2
                            break

                if not ajax_token:
                    raise Exception("TOKEN_MISSING: Could not extract ajaxToken after multiple waits.")

                if not sec_header_val:
                    sec_header_val = extract_sec_cookie(dict(session._curl_session.cookies)) or ""

                headers = {
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": "https://aternos.org/server/",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                }
                if sec_header_val:
                    headers["SEC"] = sec_header_val

                human_delay(800, 2000)

                if action_type == "start":
                    url = f"https://aternos.org/panel/ajax/start.php?headstart=0&access-credits=0&token={ajax_token}"
                elif action_type == "stop":
                    url = f"https://aternos.org/panel/ajax/stop.php?token={ajax_token}"
                else:
                    raise Exception(f"Unknown action: {action_type}")

                res = session.get(url, headers=headers)
                log.info("%s response: %d", action_type, res.status)

                if res.status == 403:
                    log.warning("Got 403 on %s AJAX. Cloudflare may be blocking.", action_type)
                    time.sleep(random.uniform(5, 10))
                    continue

                return res.status

        except Exception as e:
            if attempt < 2:
                log.warning("Action attempt %d failed: %s. Retrying...", attempt + 1, e)
                time.sleep(random.uniform(3, 7))
                continue
            raise

    raise Exception(f"All action attempts failed for {action_type}")


def execute_aternos_scrapling(
    action_type: str,
    username: str,
    password: str,
    session_token: str | None,
    state_file: str,
    proxy_url: str | None,
    update_status_sync,
) -> None:
    all_cookies = {}

    for attempt in range(ATERNOS_MAX_RETRIES + 1):
        try:
            if attempt == 0:
                update_status_sync(f"Validating session...\n{make_progress_bar(20)}")
                session_valid = validate_session(session_token, proxy_url)
            else:
                session_valid = False

            if not session_valid:
                update_status_sync(f"Logging in to Aternos (attempt {attempt + 1})...\n{make_progress_bar(30)}")
                try:
                    all_cookies, new_token = aternos_login(username, password, proxy_url, state_file)
                    if new_token:
                        session_token = new_token
                except Exception as login_err:
                    log.error("Login failed on attempt %d: %s", attempt + 1, login_err)
                    if attempt < ATERNOS_MAX_RETRIES:
                        update_status_sync(f"Login blocked, rotating fingerprint...\n{make_progress_bar(25)}")
                        human_delay(5000, 10000)
                        continue
                    raise
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
            if "SESSION_EXPIRED" in err_msg and attempt < ATERNOS_MAX_RETRIES:
                log.warning("Session died mid-flow, retrying... (attempt %d)", attempt + 2)
                session_token = None
                all_cookies = {}
                human_delay(2000, 5000)
                continue
            if "TOKEN_MISSING" in err_msg or "SEC_MISSING" in err_msg:
                if attempt < ATERNOS_MAX_RETRIES:
                    log.warning("Token extraction failed, retrying with fresh session... (attempt %d)", attempt + 2)
                    session_token = None
                    all_cookies = {}
                    clear_cookies()
                    human_delay(3000, 7000)
                    continue
            raise

    raise Exception("All retry attempts exhausted. Cloudflare may be blocking this IP.")


async def run_aternos_action(ctx, action_type: str, status_msg, proxy_url: str | None) -> None:
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
        try:
            asyncio.run_coroutine_threadsafe(status_msg.edit(content=message), loop)
        except Exception:
            pass

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
        traceback.print_exc()
        err = str(e)
        if "TOKEN_MISSING" in err or "SEC_MISSING" in err:
            await status_msg.edit(content="Aternos changed their page structure. Needs code update.")
        elif "SESSION_EXPIRED" in err:
            await status_msg.edit(content="Session expired and re-login failed. Check credentials.")
        elif "Cloudflare" in err or "cloudflare" in err:
            await status_msg.edit(content="Cloudflare is blocking this IP. Try rotating proxies or waiting.")
        elif "login" in err.lower():
            await status_msg.edit(content="Login failed. Check ATERNOS_USER/ATERNOS_PASS.")
        else:
            await status_msg.edit(content=f"Automation failed: {err[:1900]}")
