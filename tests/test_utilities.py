import logging
from unittest import TestCase
import sys
from ts3API import utilities


def test_escape_all():
    """
    Simple test: just concatenate all values and check the escaping
    """
    unescaped = ""
    expected = r""
    for v, r in utilities._ESCAPE_MAP:
        unescaped += v
        expected += r
    assert utilities.escape(unescaped) == expected


def test_unescape_all():
    """
    Simple test: just concatenate all replacements and check the unescaping
    """
    escaped = ""
    expected = r""
    for v, r in utilities._ESCAPE_MAP:
        expected += v
        escaped += r
    assert utilities.unescape(escaped) == expected


def test_escape_order():
    """
    Check if the order of escaping is correct.
    """
    unescaped = "\\r\n"
    expected = "\\\\r\\n"
    assert utilities.escape(unescaped) == expected


def test_escape_whitespace():
    """
    Check whitespace escaping.
    """
    unescaped = "Test string\twith whitespace"
    expected = r"Test\sstring\twith\swhitespace"
    assert utilities.escape(unescaped) == expected
