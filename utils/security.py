import hmac
import re


def constant_time_compare(val1: str, val2: str) -> bool:
    return hmac.compare_digest(val1.encode(), val2.encode())


def sanitize_display_name(name: str) -> str:
    cleaned = re.sub(r'[^\w\s\-.,!?]', '', name)
    return cleaned[:50] if cleaned else "Anonymous"
