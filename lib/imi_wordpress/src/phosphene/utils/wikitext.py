"""Domain-agnostic Wikitext markup formatting utilities.

Pure functions with zero domain dependencies.

OKR: @okr_publish_pipeline
"""

from __future__ import annotations

from collections.abc import Mapping


def render_wikitext_template(
    template_name: str,
    parameters: Mapping[str, str],
    body: str = "",
) -> str:
    """Render a standard MediaWiki template with parameters.

        Formats as {{TemplateName|Key=Value|...}}

    Body
        or {{TemplateName}}

    Body when parameters is empty.

        Args:
            template_name: Name of the template (e.g. 'Article', 'Preprint').
            parameters: Key-value parameter mapping.
            body: Optional following wikitext body.

        Returns:
            Formatted wikitext string.
    """
    param_tokens = [f"{k}={v}" for k, v in parameters.items()]
    if param_tokens:
        template_str = "{{" + template_name + "|" + "|".join(param_tokens) + "}}"
    else:
        template_str = "{{" + template_name + "}}"

    if body and body.strip():
        return f"{template_str}\n\n{body.strip()}"
    return template_str
