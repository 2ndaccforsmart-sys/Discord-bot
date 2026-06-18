from utils.aternos import extract_ajax_token, extract_sec_cookie, is_login_page, is_cloudflare_challenge


def test_extract_ajax_token_found():
    html = 'var ajaxToken = "abc123def456ghi789";'
    assert extract_ajax_token(html) == "abc123def456ghi789"


def test_extract_ajax_token_window():
    html = 'window.ajaxToken = "xyz789abcdefgh";'
    assert extract_ajax_token(html) == "xyz789abcdefgh"


def test_extract_ajax_token_not_found():
    html = "<html><body>No token here</body></html>"
    assert extract_ajax_token(html) is None


def test_extract_ajax_token_too_short():
    html = 'var token = "short";'
    assert extract_ajax_token(html) is None


def test_extract_sec_cookie_found():
    cookies = {"ATERNOS_SEC_abcd": "tokenvalue"}
    result = extract_sec_cookie(cookies)
    assert result == "abcd:tokenvalue"


def test_extract_sec_cookie_xsrf():
    cookies = {"XSRF-TOKEN": "xsrfvalue"}
    result = extract_sec_cookie(cookies)
    assert result == "xsrfvalue"


def test_extract_sec_cookie_not_found():
    cookies = {"SESSION_ID": "abc123"}
    assert extract_sec_cookie(cookies) is None


def test_is_login_page_by_url():
    assert is_login_page("https://aternos.org/login/", "") is True


def test_is_login_page_by_password_field():
    assert is_login_page("", 'type="password"') is True


def test_is_login_page_not_login():
    assert is_login_page("https://aternos.org/server/", "<h1>Server</h1>") is False


def test_is_cloudflare_challenge_turnstile():
    assert is_cloudflare_challenge("", "Just a moment... Checking if the site connection is secure") is True


def test_is_cloudflare_challenge_url():
    assert is_cloudflare_challenge("https://example.com/cf-challenge-platform", "") is True


def test_is_cloudflare_challenge_not_cf():
    assert is_cloudflare_challenge("https://aternos.org/server/", "<h1>Server Panel</h1>") is False


def test_is_cloudflare_challenge_verify_human():
    assert is_cloudflare_challenge("", "Please verify you are human") is True


def test_is_cloudflare_challenge_empty():
    assert is_cloudflare_challenge("", "") is False
