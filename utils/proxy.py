import os


def get_configured_proxy() -> str | None:
    proxy_url = os.getenv("PROXY_SERVER")
    if not proxy_url:
        proxy_user = os.getenv("PROXY_USER")
        proxy_pass = os.getenv("PROXY_PASS")
        proxy_host = os.getenv("PROXY_HOST")
        proxy_port = os.getenv("PROXY_PORT")

        if proxy_user and proxy_pass and proxy_host and proxy_port:
            proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
        elif proxy_host and proxy_port:
            proxy_url = f"http://{proxy_host}:{proxy_port}"
    return proxy_url


def sanitize_proxy_url(url: str | None) -> str:
    if not url:
        return "none"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.password:
            return f"{parsed.scheme}://{parsed.username}:***@{parsed.hostname}:{parsed.port}"
        return url
    except Exception:
        return "***"
