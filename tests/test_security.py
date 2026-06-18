from utils.security import constant_time_compare, sanitize_display_name


def test_constant_time_compare_equal():
    assert constant_time_compare("hello", "hello") is True


def test_constant_time_compare_not_equal():
    assert constant_time_compare("hello", "world") is False


def test_constant_time_compare_empty():
    assert constant_time_compare("", "") is True


def test_sanitize_display_name_normal():
    assert sanitize_display_name("Daksh") == "Daksh"


def test_sanitize_display_name_special_chars():
    result = sanitize_display_name("<script>alert('xss')</script>")
    assert "<" not in result
    assert ">" not in result


def test_sanitize_display_name_long():
    name = "A" * 100
    result = sanitize_display_name(name)
    assert len(result) <= 50


def test_sanitize_display_name_empty():
    result = sanitize_display_name("")
    assert result == "Anonymous"
