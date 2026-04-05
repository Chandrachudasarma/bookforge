"""HTML Cleaner — first sub-step of Stage 2 (Normalize).

Strips non-semantic elements (scripts, nav, ads), normalises attributes,
and returns well-formed HTML ready for structure detection.
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Comment, Tag

# Tags to remove entirely (including their children)
_STRIP_TAGS = frozenset([
    "script", "style", "noscript", "nav", "header", "footer",
    "aside", "form", "button", "select", "input", "textarea",
    "iframe", "embed", "object", "applet", "link", "meta",
])

# Attributes to keep per tag (all others stripped except bf-* classes)
_KEEP_ATTRS: dict[str, set[str]] = {
    "a": {"href"},
    "img": {"src", "alt", "width", "height"},
    "table": set(),
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "ol": {"start", "type"},
    "li": {"value"},
    "h1": set(), "h2": set(), "h3": set(), "h4": set(), "h5": set(), "h6": set(),
    "p": set(),
    "blockquote": set(),
    "pre": set(),
    "code": set(),
    "figure": set(),
    "figcaption": set(),
    "section": set(),
    "article": set(),
    "div": set(),
    "span": set(),
    "strong": set(), "b": set(),
    "em": set(), "i": set(),
    "ul": set(),
    "dl": set(), "dt": set(), "dd": set(),
    "br": set(),
    "hr": set(),
    "sup": set(),
    "sub": set(),
    "thead": set(), "tbody": set(), "tfoot": set(), "tr": set(),
}


def clean_html(raw_html: str) -> str:
    """Strip non-semantic markup and return clean HTML string."""
    soup = BeautifulSoup(raw_html, "lxml")

    # Remove HTML comments
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Remove strip-listed tags
    for tag_name in _STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Strip disallowed attributes from remaining tags
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        _clean_attrs(tag)

    # Extract the body content (or full document if no body)
    body = soup.find("body") or soup
    return str(body)


def _clean_attrs(tag: Tag) -> None:
    """Remove attributes not in the allow-list for this tag.

    bf-* classes (e.g. bf-protected) are always preserved.
    """
    allowed = _KEEP_ATTRS.get(tag.name, set())
    attrs_to_remove = []

    for attr in list(tag.attrs.keys()):
        if attr in allowed:
            continue
        # Preserve bf-* class markers added by later normalization steps
        if attr == "class":
            classes = tag.get("class", [])
            if isinstance(classes, list):
                bf_classes = [c for c in classes if c.startswith("bf-")]
                if bf_classes:
                    tag["class"] = bf_classes
                    continue
            attrs_to_remove.append(attr)
            continue
        # Preserve data-* attributes that start with "data-bf"
        if attr.startswith("data-bf"):
            continue
        attrs_to_remove.append(attr)

    for attr in attrs_to_remove:
        del tag[attr]
