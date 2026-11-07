"""Sandboxed Jinja2 rendering. Pure Python, no NetBox imports."""
from __future__ import annotations

from jinja2 import StrictUndefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment


class RenderError(ValueError):
    """The template could not be rendered (syntax error or missing variable)."""


def render(template_text: str, context: dict) -> str:
    env = SandboxedEnvironment(
        undefined=StrictUndefined,  # a missing variable is an error, never an empty string
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        comment_start_string="{##",  # '#' is used a lot in ISC configs
        comment_end_string="##}",
        autoescape=False,
    )
    try:
        return env.from_string(template_text).render(**context)
    except TemplateError as exc:
        raise RenderError(f"{type(exc).__name__}: {exc}") from exc
