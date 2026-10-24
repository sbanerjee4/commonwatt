"""In-app message text and the forbidden-word safety check.

Safety (safety.md): no user-facing text may contain "cut", "shut off",
"curtail", or "disconnect". validate_templates() runs at import so a forbidden
word fails fast. (The SMS templates and the 160-char limit were removed when
SMS was dropped; only the in-app "ask" text remains.)
"""

from __future__ import annotations

import re

FORBIDDEN_WORDS = ("cut", "shut off", "curtail", "disconnect")

# The opening "ask" posted into the thread when an approved event includes a
# building. In-app, so no length cap. Rendered with the event's own values.
TEMPLATES: dict[str, str] = {
    "building_ask": (
        "CommonWatt event {window}. {building_name} is asked to reduce "
        "{kw_requested} of {kw_enrolled} kW. {reason}. Estimated payment "
        "${payment}. Reply YES, NO, or a kW amount — participation is "
        "voluntary and paid."
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

    Raises KeyError if a required placeholder is missing, ValueError if the
    rendered body is empty or (defensively) contains a forbidden word after
    substitution.
    """
    template = get_template(template_name)
    try:
        body = template.format(**params)
    except KeyError as exc:
        raise KeyError(
            f"missing param for template {template_name!r}: {exc}"
        ) from exc

    if not body:
        raise ValueError("rendered body is empty")

    forbidden = _contains_forbidden(body)
    if forbidden is not None:
        raise ValueError(
            f"rendered body contains forbidden word {forbidden!r}"
        )
    return body


# Fail fast at import: a forbidden word in a template must never ship.
validate_templates()
