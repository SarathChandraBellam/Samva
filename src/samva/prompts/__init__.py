"""Prompt templates for Samva voice agent personas.

Each template is a .py module in this package exposing a ``PROMPT`` string.
Use :func:`load_prompt` to retrieve a template by name and :func:`list_prompts`
to enumerate available templates.

Adding a new template
---------------------
1. Create ``src/samva/prompts/my_template.py`` with a ``PROMPT = "..."`` string.
2. It becomes immediately available via ``load_prompt("my_template")``.
"""
from __future__ import annotations

import importlib
from pathlib import Path

_HERE = Path(__file__).parent

# Names that are not prompt templates
_EXCLUDED = {"__init__"}


def list_prompts() -> list[str]:
    """Return the names of all available prompt templates."""
    return sorted(
        p.stem
        for p in _HERE.glob("*.py")
        if p.stem not in _EXCLUDED
    )


def load_prompt(name: str = "default") -> str:
    """
    Load and return the PROMPT string from ``samva.prompts.<name>``.

    Parameters
    ----------
    name:
        Template name (filename without ``.py``), e.g. ``"sales"``.

    Raises
    ------
    ValueError
        If the template does not exist.
    """
    available = list_prompts()
    if name not in available:
        raise ValueError(
            f"Prompt template '{name}' not found. "
            f"Available templates: {', '.join(available)}"
        )
    module = importlib.import_module(f".{name}", package=__name__)
    prompt: str = getattr(module, "PROMPT", "")
    if not prompt:
        raise ValueError(f"Prompt template '{name}' has an empty PROMPT string.")
    return prompt


__all__ = ["load_prompt", "list_prompts"]
