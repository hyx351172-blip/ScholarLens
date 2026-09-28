"""Bounded, unique whitespace alignment; no fuzzy or semantic text repair."""

VERSION = 'ascii_whitespace_quote_alignment_v1'
WHITESPACE = frozenset(' \t\r\n')
MAX_QUOTE_CHARS = 1200
MAX_SOURCE_CHARS = 64000


def _collapse(text):
    """Each normalized character maps to a half-open ORIGINAL codepoint span."""
    chars, spans = [], []
    index = 0
    while index < len(text):
        start = index
        if text[index] in WHITESPACE:
            index += 1
            while index < len(text) and text[index] in WHITESPACE:
                index += 1
            chars.append(' ')
        else:
            chars.append(text[index])
            index += 1
        spans.append((start, index))
    return ''.join(chars), spans


def align_quote(quote, source, *, source_start=0):
    """Return source quote + offsets; retain the untouched model quote separately.

    No trimming: separators remain separators, never disappear or get invented.
    An exact occurrence is insufficient if another normalized occurrence exists.
    Coordinates are Python Unicode codepoints, consistent with v2 source spans.
    """
    if (not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE_CHARS
            or not isinstance(source, str) or not 1 <= len(source) <= MAX_SOURCE_CHARS
            or type(source_start) is not int or source_start < 0):
        raise ValueError('invalid_quote_alignment_input')
    normalized_source, spans = _collapse(source)
    normalized_quote, _ = _collapse(quote)
    start = normalized_source.find(normalized_quote)
    if start < 0:
        raise ValueError('missing_quote')
    if normalized_source.find(normalized_quote, start + 1) >= 0:
        raise ValueError('ambiguous_quote')
    original_start = spans[start][0]
    original_end = spans[start + len(normalized_quote) - 1][1]
    original = source[original_start:original_end]
    if len(original) > MAX_QUOTE_CHARS:
        raise ValueError('aligned_quote_too_long')
    return dict(model_quote=quote, quote=original,
                match_mode='exact' if original == quote else 'whitespace_only',
                source_start=source_start + original_start, source_end=source_start + original_end)
