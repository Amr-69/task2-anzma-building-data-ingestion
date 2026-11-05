import re

_ARABIC = re.compile(r"[\u0600-\u06FF]")
_LATIN = re.compile(r"[A-Za-z]")
# Protected technical tokens (asset codes, metric names, timestamps) stay English.
_PROTECTED = re.compile(r"\b[A-Za-z0-9]*[-_:.0-9][A-Za-z0-9_\-:.]*\b")


def detect_language(text):
    """Return 'ar' or 'en' by the dominant script, ignoring technical tokens."""

    cleaned = _PROTECTED.sub(" ", text)
    arabic = len(_ARABIC.findall(cleaned))
    latin = len(_LATIN.findall(cleaned))
    return "ar" if arabic > latin else "en"