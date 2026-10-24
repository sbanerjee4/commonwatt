"""Property tests for in-app templates and the reply parser."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from notify.templates import FORBIDDEN_WORDS, TEMPLATES
from notify.validation import parse_reply_body


def test_no_template_contains_forbidden_word():
    for name, body in TEMPLATES.items():
        low = body.lower()
        for word in FORBIDDEN_WORDS:
            assert word not in low, f"{name} contains {word!r}"


@settings(max_examples=200, deadline=None)
@given(st.text())
def test_parser_is_total(body):
    # Never raises; always a str, positive int, or None.
    out = parse_reply_body(body)
    assert out is None or isinstance(out, (str, int))
    if isinstance(out, int):
        assert out > 0


@settings(max_examples=100, deadline=None)
@given(st.integers(min_value=1, max_value=99999))
def test_parser_reads_kw_numbers(n):
    assert parse_reply_body(str(n)) == n
    assert parse_reply_body(f"{n} kw") == n
    assert parse_reply_body(f"  {n}KW ") == n


@settings(max_examples=100, deadline=None)
@given(st.integers(max_value=0))
def test_parser_rejects_nonpositive(n):
    assert parse_reply_body(str(n)) is None
