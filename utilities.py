"""Utility variables and functions for the TS3 API"""

# FROM OLD API
"""
Don't change the order in this map, otherwise it might break
"""
_ESCAPE_MAP = [
    ("\\", r"\\"),
    ("/", r"\/"),
    (" ", r"\s"),
    ("|", r"\p"),
    ("\a", r"\a"),
    ("\b", r"\b"),
    ("\f", r"\f"),
    ("\n", r"\n"),
    ("\r", r"\r"),
    ("\t", r"\t"),
    ("\v", r"\v")
    ]


def escape(raw):
    """
    Escapes characters that need escaping according to _ESCAPE_MAP
    """
    for char, replacement in _ESCAPE_MAP:
        raw = raw.replace(char, replacement)
    return raw


def unescape(raw):
    """
    Undo escaping of characters according to _ESCAPE_MAP
    """
    for replacement, char in reversed(_ESCAPE_MAP):
        raw = raw.replace(char, replacement)
    return raw


class TS3Exception(Exception):
    pass

class TS3ConnectionClosedException(Exception):
    pass
