"""Tests for equation detection in Stage 2 normalization."""

from bookforge.normalization.equation_detector import detect_equations


def test_detects_latex_inline():
    html = "<p>The formula $E = mc^2$ is famous.</p>"
    result, blocks, _ = detect_equations(html)
    assert len(blocks) == 1
    assert blocks[0].source_format == "latex_inline"
    assert "bf-protected" in result


def test_detects_latex_display():
    html = "<p>See equation:</p><p>$$\\int_0^\\infty f(x)dx$$</p>"
    result, blocks, _ = detect_equations(html)
    assert any(b.source_format == "latex_display" for b in blocks)


def test_does_not_match_dollar_amounts():
    html = "<p>The item costs $5.00 and $10.00.</p>"
    result, blocks, _ = detect_equations(html)
    # Dollar amounts should not be tagged as equations
    assert len(blocks) == 0


def test_detects_mathml():
    html = '<p>See <math><mi>E</mi><mo>=</mo><mi>m</mi><msup><mi>c</mi><mn>2</mn></msup></math>.</p>'
    result, blocks, _ = detect_equations(html)
    assert any(b.source_format == "mathml" for b in blocks)


def test_block_counter_increments():
    html = "<p>$x$ and $y$ and $z$</p>"
    result, blocks, counter = detect_equations(html, block_counter=5)
    # Counter should start at 5 and increment
    assert blocks[0].block_id == "PROTECTED_5"
    assert counter == 5 + len(blocks)
