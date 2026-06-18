from utils.config import _safe_int, is_valid_server_name


def test_safe_int_valid():
    import os
    os.environ["TEST_INT_VAR"] = "42"
    assert _safe_int("TEST_INT_VAR", 0) == 42
    del os.environ["TEST_INT_VAR"]


def test_safe_int_invalid():
    import os
    os.environ["TEST_INT_VAR"] = "abc"
    assert _safe_int("TEST_INT_VAR", 99) == 99
    del os.environ["TEST_INT_VAR"]


def test_safe_int_missing():
    assert _safe_int("NONEXISTENT_VAR_12345", 77) == 77


def test_is_valid_server_name_valid():
    assert is_valid_server_name("MyServer") is True
    assert is_valid_server_name("server_1") is True
    assert is_valid_server_name("a") is True


def test_is_valid_server_name_invalid():
    assert is_valid_server_name("") is False
    assert is_valid_server_name("my server") is False
    assert is_valid_server_name("server!@#") is False
    assert is_valid_server_name("a" * 65) is False
