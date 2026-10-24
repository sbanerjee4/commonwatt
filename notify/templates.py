"""SMS templates and rendering.

Safety (safety.md): no user-facing text may contain "cut", "shut off",
"curtail", or "disconnect". validate_templates() runs at import so a
forbidden word fails fast, before anything is sent.
"""

from __future__ import annotations

import re

MAX_SMS_LENGTH = 160

FORBIDDEN_WORDS = ("cut", "shut off", "curtail", "disconnect")

TEMPLATES: dict[str, str] = {
    "building_ask": (
        "CommonWatt: event {window}. {building_name}: reduce {kw_requested} of "
        "{kw_enrolled} kW. {reason}. Est. ${payment}. Reply YES, NO, or kW."
    ),
    "operator_draft_ready": (
        "CommonWatt: draft event ready. {window}, {target_mw} MW, "
        "{building_count} buildings, EJ share {ej_share}%. Approve in dashboard."
    ),
    "operator_backfill": (
        "CommonWatt: {decline_count} declines (-{shortfall_mw} MW). "
        "Backfill proposed, needs approval."
    ),
    "operator_unreachable": (
        "CommonWatt: target unreachable under the {cap}% EJ cap. "
        "Achievable {achievable_mw} MW. Raise cap or accept."
    ),
}


def get_template(template_name: str) -> str:
    """Return the template string. Raise KeyError if unknown."""
    if template_name not in TEMPLATES:
        raise KeyError(f"unknown template: {template_name!r}")
    return TEMPLATES[template_name]


def _contains_forbidden(text: str) -> str | None:
    """Return the first forbidden word present (case-insensitive), else None.

    Word-boundary match so "cut" does not trip on "executed".
    """
    lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lower):
            return word
    return None


def validate_templates() -> None:
    """Assert no template contains a forbidden word. Raises ValueError."""
    for name, body in TEMPLATES.items():
        found = _contains_forbidden(body)
        if found is not None:
            raise ValueError(
                f"template {name!r} contains forbidden word {found!r}"
            )


def render_template(template_name: str, params: dict) -> str:
    """Render a template with params.

    Raises KeyError if a required placeholder is missing from params,
    ValueError if the rendered body is empty, exceeds MAX_SMS_LENGTH,
    or (defensively) contains a forbidden word after substitution.
    """
    template = get_template(template_name)
    try:
        body = template.format(**params)
    except KeyError as exc:
        raise KeyError(
            f"missing param for template {template_name!r}: {exc}"
        ) from exc

    if not body:
        raise ValueError("rendered SMS body is empty")

    forbidden = _contains_forbidden(body)
    if forbidden is not None:
        raise ValueError(
            f"rendered body contains forbidden word {forbidden!r}"
        )

    if len(body) > MAX_SMS_LENGTH:
        raise ValueError(
            f"rendered body is {len(body)} chars, exceeds {MAX_SMS_LENGTH}"
        )
    return body


# Fail fast at import: a forbidden word in a template must never ship.
validate_templates()
