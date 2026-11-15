"""Sandboxed Jinja2 rendering. Pure Python, no NetBox imports."""
from __future__ import annotations

from jinja2 import StrictUndefined
from jinja2.exceptions import TemplateError
from jinja2.sandbox import SandboxedEnvironment


class RenderError(ValueError):
    """The template could not be rendered (syntax error or missing variable)."""


_ENV = SandboxedEnvironment(
    undefined=StrictUndefined,  # a missing variable is an error, never an empty string
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
    comment_start_string="{##",  # '#' is used a lot in ISC configs
    comment_end_string="##}",
    autoescape=False,
)
_COMPILED: dict = {}  # code text -> compiled template (the same pool code is rendered for hundreds of subnets)


def _template(text):
    tpl = _COMPILED.get(text)
    if tpl is None:
        if len(_COMPILED) > 500:
            _COMPILED.clear()
        tpl = _COMPILED[text] = _ENV.from_string(text)
    return tpl


def render(template_text: str, context: dict) -> str:
    try:
        return _template(template_text).render(**context)
    except TemplateError as exc:
        raise RenderError(f"{type(exc).__name__}: {exc}") from exc
