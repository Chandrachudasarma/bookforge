"""Tests for protected block extract → placeholder → restore round-trip.

These must pass before connecting to AI — they verify the isolation
mechanism that keeps equations and tables intact through rewriting.
"""

from bookforge.ai.rewriter import extract_protected_blocks, restore_protected_blocks


def test_extract_restores_equation_losslessly():
    html = (
        '<p>Some text <span class="bf-protected" data-type="equation" '
        'data-block-id="PROTECTED_0">$E = mc^2$</span> after.</p>'
    )
    cleaned, placeholders = extract_protected_blocks(html)

    assert "PROTECTED_0" in cleaned or "<<<PROTECTED_0>>>" in cleaned
    assert "$E = mc^2$" not in cleaned

    restored = restore_protected_blocks(cleaned, placeholders)
    assert "$E = mc^2$" in restored


def test_extract_restores_table_losslessly():
    html = (
        '<p>Before table.</p>'
        '<table class="bf-protected" data-type="table" data-block-id="PROTECTED_1">'
        '<tr><td>A</td><td>B</td></tr>'
        '</table>'
        '<p>After table.</p>'
    )
    cleaned, placeholders = extract_protected_blocks(html)
    assert len(placeholders) == 1

    restored = restore_protected_blocks(cleaned, placeholders)
    assert "<td>A</td>" in restored
    assert "<td>B</td>" in restored


def test_multiple_blocks_all_restored():
    html = (
        '<span class="bf-protected" data-type="equation" data-block-id="PROTECTED_0">$x$</span>'
        '<span class="bf-protected" data-type="equation" data-block-id="PROTECTED_1">$y$</span>'
        '<span class="bf-protected" data-type="equation" data-block-id="PROTECTED_2">$z$</span>'
    )
    cleaned, placeholders = extract_protected_blocks(html)
    assert len(placeholders) == 3

    restored = restore_protected_blocks(cleaned, placeholders)
    assert "$x$" in restored
    assert "$y$" in restored
    assert "$z$" in restored


def test_no_protected_blocks_unchanged():
    html = "<p>Plain text with no equations.</p>"
    cleaned, placeholders = extract_protected_blocks(html)
    assert len(placeholders) == 0
    restored = restore_protected_blocks(cleaned, placeholders)
    assert "Plain text with no equations." in restored
