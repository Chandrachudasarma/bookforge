"""Template loader — loads and validates template directories.

Each template is a directory under templates/ containing:
  config.yaml          — template metadata and settings
  styles.css           — EPUB/PDF stylesheet
  print.css            — PDF-only print stylesheet (optional)
  *.html.jinja         — Jinja templates for front matter sections
  fonts/               — embedded TTF/OTF fonts (optional)
  docx_reference.docx  — DOCX style reference document (optional)

The Template dataclass is passed to exporters and the structure builder
for CSS application and Jinja rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import jinja2
import jinja2.meta
import yaml

from bookforge.core.exceptions import TemplateError
from bookforge.core.logging import get_logger

logger = get_logger("templates.loader")

# BookMetadata fields allowed in Jinja templates
_ALLOWED_JINJA_VARS = {
    "title", "subtitle", "authors", "isbn", "eisbn",
    "publisher_name", "publisher_address", "publisher_email",
    "year", "language", "cover_image",
}


@dataclass
class TemplateConfig:
    """Parsed config.yaml for a template."""

    display_name: str = ""
    description: str = ""
    font_family: str = "Georgia, serif"
    font_size: str = "11pt"
    line_height: str = "1.5"
    page_margins: dict = field(default_factory=lambda: {
        "top": "2cm", "bottom": "2cm", "left": "2.5cm", "right": "2cm",
    })


@dataclass
class Template:
    """A loaded and validated template."""

    name: str
    directory: Path
    config: TemplateConfig
    styles_css: Path
    print_css: Path | None
    docx_reference: Path | None
    fonts: list[Path]
    jinja_env: jinja2.Environment


def load_template(name: str, templates_dir: Path | None = None) -> Template:
    """Load a template directory into a Template object.

    Validates at load time:
      - config.yaml exists and is valid
      - styles.css exists
      - Jinja templates only reference allowed variables

    Args:
        name:          Template name (e.g. "academic", "modern").
        templates_dir: Parent directory containing template subdirs.
                       Defaults to templates/ in the project root.

    Raises:
        TemplateError: If the template is invalid or missing.
    """
    if templates_dir is None:
        templates_dir = _find_templates_dir()

    template_dir = templates_dir / name
    if not template_dir.is_dir():
        raise TemplateError(f"Template not found: {name} (looked in {templates_dir})")

    # Load config.yaml
    config_path = template_dir / "config.yaml"
    if not config_path.exists():
        raise TemplateError(f"Template '{name}' missing config.yaml")

    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise TemplateError(f"Invalid config.yaml in template '{name}': {exc}") from exc

    config = TemplateConfig(**{
        k: v for k, v in raw_config.items() if k in TemplateConfig.__dataclass_fields__
    })

    # Validate styles.css
    styles_css = template_dir / "styles.css"
    if not styles_css.exists():
        raise TemplateError(f"Template '{name}' missing styles.css")

    # print.css is optional
    print_css = template_dir / "print.css"
    print_css = print_css if print_css.exists() else None

    # docx_reference.docx is optional
    docx_ref = template_dir / "docx_reference.docx"
    docx_ref = docx_ref if docx_ref.exists() else None

    # Fonts
    fonts_dir = template_dir / "fonts"
    fonts: list[Path] = []
    if fonts_dir.is_dir():
        fonts = list(fonts_dir.glob("*.ttf")) + list(fonts_dir.glob("*.otf"))

    # Build Jinja environment
    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=jinja2.select_autoescape(["html", "jinja"]),
        undefined=jinja2.StrictUndefined,
    )

    # Validate Jinja templates at load time
    for jinja_file in template_dir.glob("*.jinja"):
        _validate_jinja_template(jinja_file, jinja_env, name)

    logger.debug(
        "Template loaded",
        name=name,
        styles=styles_css.exists(),
        print_css=print_css is not None,
        fonts=len(fonts),
        jinja_count=len(list(template_dir.glob("*.jinja"))),
    )

    return Template(
        name=name,
        directory=template_dir,
        config=config,
        styles_css=styles_css,
        print_css=print_css,
        docx_reference=docx_ref,
        fonts=fonts,
        jinja_env=jinja_env,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_jinja_template(path: Path, env: jinja2.Environment, template_name: str) -> None:
    """Parse a Jinja template and verify variables are from the allowed set."""
    try:
        source = path.read_text(encoding="utf-8")
        ast = env.parse(source)
        referenced = jinja2.meta.find_undeclared_variables(ast)
        invalid = referenced - _ALLOWED_JINJA_VARS
        if invalid:
            raise TemplateError(
                f"Template '{template_name}/{path.name}' references unknown "
                f"variables: {invalid}. Allowed: {_ALLOWED_JINJA_VARS}"
            )
    except TemplateError:
        raise
    except Exception as exc:
        raise TemplateError(
            f"Cannot parse Jinja template '{template_name}/{path.name}': {exc}"
        ) from exc


def _find_templates_dir() -> Path:
    """Find the templates/ directory relative to the project root."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / "pyproject.toml").exists():
            return parent / "templates"
    return cwd / "templates"
