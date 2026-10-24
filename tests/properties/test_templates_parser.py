"""Property tests for templates, parser, and signature validation."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from notify.templates import FORBIDDEN_WORDS, TEMPLATES, render_template
from notify.validation import parse_reply_body, validate_signature


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


@settings(max_examples=100, deadline=None)
@given(st.binary(min_size=1), st.text(min_size=1))
def test_signature_rejects_wrong(body, sig):
    # A random signature must not validate — unless it happens to equal the
    # true one (negligible), which we exclude so the property is exact.
    import base64, hashlib, hmac
    from urllib.parse import parse_qsl
    token = "secret"
    url = "https://commonwatt.example.com/sms/inbound"
    params = sorted(parse_qsl(body.decode("utf-8", "replace"), keep_blank_values=True))
    payload = url + "".join(k + v for k, v in params)
    true_sig = base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()
    if sig == true_sig or not sig.isascii():
        return
    assert validate_signature(body, sig, auth_token=token, url=url) is False


def test_building_ask_fits_160():
    body = render_template(
        "building_ask",
        dict(window="Tue 2-6PM", building_name="Elm St", kw_requested=20,
             kw_enrolled=100, reason="peak day", payment=200),
    )
    assert len(body) <= 160
