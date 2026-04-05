"""Tests for the template loader."""

from pathlib import Path

import pytest

from bookforge.core.exceptions import TemplateError
from bookforge.templates.loader import Template, load_template


# ---------------------------------------------------------------------------
# Fixtures — create template directories
# ---------------------------------------------------------------------------


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    """Create a templates directory with a valid 'test' template."""
    tpl_dir = tmp_path / "templates" / "test"
    tpl_dir.mkdir(parents=True)

    (tpl_dir / "config.yaml").write_text(
        "display_name: Test Template\n"
        "description: A test template\n"
        "font_family: Georgia, serif\n"
    )
    (tpl_dir / "styles.css").write_text(
        "body { font-family: Georgia, serif; }\n"
        "table { border-collapse: collapse; }\n"
    )
    (tpl_dir / "print.css").write_text(
        "@page { size: A5; margin: 2cm; }\n"
    )
    (tpl_dir / "title_page.html.jinja").write_text(
        '<div class="title-page">'
        "<h1>{{ title }}</h1>"
        "<p>{{ authors | join(', ') }}</p>"
        "<p>{{ publisher_name }}</p>"
        "</div>"
    )
    (tpl_dir / "copyright.html.jinja").write_text(
        '<div class="copyright">'
        "<p>Copyright {{ year }} {{ publisher_name }}</p>"
        "{% if isbn %}<p>ISBN: {{ isbn }}</p>{% endif %}"
        "</div>"
    )

    return tmp_path / "templates"


@pytest.fixture
def minimal_template_dir(tmp_path: Path) -> Path:
    """Template with only the required files (config.yaml + styles.css)."""
    tpl_dir = tmp_path / "templates" / "minimal"
    tpl_dir.mkdir(parents=True)

    (tpl_dir / "config.yaml").write_text("display_name: Minimal\n")
    (tpl_dir / "styles.css").write_text("body { font-size: 10pt; }\n")

    return tmp_path / "templates"


# ---------------------------------------------------------------------------
# Tests — loading
# ---------------------------------------------------------------------------


def test_loads_valid_template(templates_dir):
    tpl = load_template("test", templates_dir)
    assert isinstance(tpl, Template)
    assert tpl.name == "test"
    assert tpl.config.display_name == "Test Template"
    assert tpl.styles_css.exists()


def test_loads_print_css_when_present(templates_dir):
    tpl = load_template("test", templates_dir)
    assert tpl.print_css is not None
    assert tpl.print_css.exists()


def test_print_css_none_when_absent(minimal_template_dir):
    tpl = load_template("minimal", minimal_template_dir)
    assert tpl.print_css is None


def test_docx_reference_none_when_absent(templates_dir):
    tpl = load_template("test", templates_dir)
    assert tpl.docx_reference is None


def test_jinja_env_renders_templates(templates_dir):
    tpl = load_template("test", templates_dir)
    jinja_tpl = tpl.jinja_env.get_template("title_page.html.jinja")
    result = jinja_tpl.render(
        title="My Book",
        authors=["Jane Doe", "John Smith"],
        publisher_name="Test Press",
        subtitle=None,
        isbn=None,
        eisbn=None,
        publisher_address=None,
        publisher_email=None,
        year=2026,
        language="en",
        cover_image=None,
    )
    assert "My Book" in result
    assert "Jane Doe" in result


def test_fonts_collected(templates_dir):
    # Add a font file
    fonts_dir = templates_dir / "test" / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "Test-Regular.ttf").write_bytes(b"fake font data")

    tpl = load_template("test", templates_dir)
    assert len(tpl.fonts) == 1
    assert tpl.fonts[0].name == "Test-Regular.ttf"


# ---------------------------------------------------------------------------
# Tests — validation errors
# ---------------------------------------------------------------------------


def test_raises_on_missing_template(templates_dir):
    with pytest.raises(TemplateError, match="Template not found"):
        load_template("nonexistent", templates_dir)


def test_raises_on_missing_config_yaml(tmp_path):
    tpl_dir = tmp_path / "templates" / "bad"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "styles.css").write_text("body {}")

    with pytest.raises(TemplateError, match="missing config.yaml"):
        load_template("bad", tmp_path / "templates")


def test_raises_on_missing_styles_css(tmp_path):
    tpl_dir = tmp_path / "templates" / "bad"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "config.yaml").write_text("display_name: Bad\n")

    with pytest.raises(TemplateError, match="missing styles.css"):
        load_template("bad", tmp_path / "templates")


def test_raises_on_invalid_jinja_variable(tmp_path):
    """Jinja templates that reference unknown variables should fail at load time."""
    tpl_dir = tmp_path / "templates" / "bad_jinja"
    tpl_dir.mkdir(parents=True)
    (tpl_dir / "config.yaml").write_text("display_name: Bad Jinja\n")
    (tpl_dir / "styles.css").write_text("body {}")
    (tpl_dir / "page.html.jinja").write_text("{{ nonexistent_variable }}")

    with pytest.raises(TemplateError, match="unknown variables"):
        load_template("bad_jinja", tmp_path / "templates")


# ---------------------------------------------------------------------------
# Tests — real templates
# ---------------------------------------------------------------------------


def test_loads_academic_template():
    """Load the actual academic template from the project's templates/ dir."""
    from bookforge.templates.loader import _find_templates_dir

    templates_dir = _find_templates_dir()
    if not (templates_dir / "academic").is_dir():
        pytest.skip("academic template not found at expected path")

    tpl = load_template("academic", templates_dir)
    assert tpl.name == "academic"
    assert tpl.config.display_name == "Academic"
    assert tpl.styles_css.exists()
    assert tpl.print_css is not None


def test_loads_modern_template():
    """Load the actual modern template from the project's templates/ dir."""
    from bookforge.templates.loader import _find_templates_dir

    templates_dir = _find_templates_dir()
    if not (templates_dir / "modern").is_dir():
        pytest.skip("modern template not found at expected path")

    tpl = load_template("modern", templates_dir)
    assert tpl.name == "modern"
    assert tpl.config.display_name == "Modern"
