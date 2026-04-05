# BookForge — Implementation Guide

**Version:** 1.1
**Date:** 2026-04-05
**Status:** In Progress

## Implementation Status

| Phase | Status | Files |
|---|---|---|
| A — Foundation | ✅ Complete | `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `config/`, `bookforge/core/` |
| B — First pipeline path (HTML→EPUB) | ✅ Complete | `ingestion/html_ingester.py`, `normalization/`, `assembly/`, `structure/`, `export/epub_exporter.py`, `core/pipeline.py` |
| C — Protected blocks | ✅ Complete | `ai/rewriter.py` (extract/restore + chunking), `normalization/equation_detector.py`, `normalization/table_standardizer.py` |
| D — All ingesters | ✅ Complete | `ingestion/markdown_ingester.py`, `txt_ingester.py`, `docx_ingester.py`, `pdf_ingester.py`, `epub_ingester.py`, `ocr_ingester.py`, `ocr/tesseract.py` |
| E — All exporters | ✅ Complete | `export/docx_exporter.py`, `docx_table_borders.py`, `pdf_exporter.py`, `equation_renderer.py`, `calibre_polish.py` |
| F — AI stage | ✅ Complete | `ai/anthropic_provider.py`, `ai/prompt_loader.py`, `ai/generators.py`, `ai/stage.py` |
| G — Metadata + Batch | ✅ Complete | `metadata/reader.py`, `metadata/validator.py`, `assembly/ordering.py` (already existed) |
| H — Template system | ✅ Complete | `templates/loader.py`, `templates/academic/`, `templates/modern/` (config.yaml + styles.css + print.css + Jinja) |
| I — Job infrastructure | ✅ Complete | `jobs/models.py`, `jobs/store.py`, `jobs/worker.py`, `jobs/manager.py` |
| J — API + UI | ✅ Complete | `api/schemas.py`, `api/routes.py`, `ui/static/index.html`, `ui/static/style.css`, `ui/static/app.js` |
| K — Polish | ✅ Complete | `ai/openai_provider.py`, `docs/TEMPLATES.md`, `docs/SETUP.md`, `tests/test_integration/` |

---

## 1. Overview

This document is the developer's guide to building BookForge from scratch. It translates the architecture into a concrete build sequence, covering what to build first, how each module should be implemented, critical implementation decisions, and known traps to avoid.

**Read before starting:**
- `ARCHITECTURE.md` — data models, stage contracts, pipeline flow (source of truth)
- `REQUIREMENTS.md` — what the client actually needs (success criteria §21)

---

## 2. Build Order

The pipeline has hard dependencies: each stage consumes the output of the previous one. Build in this order to enable end-to-end testing as early as possible.

```
Phase A — Foundation
  1. Project scaffold (pyproject.toml, Dockerfile, config loading)
  2. Core data models (all @dataclass types in core/models.py)
  3. Core exceptions (core/exceptions.py)
  4. Plugin registry (core/registry.py)

Phase B — First Pipeline Path (HTML → EPUB, no AI)
  5. Stage 1: HTML ingester
  6. Stage 2: Normalizer (HTML cleaner + structure detector only)
  7. Stage 3: Assembler (single-file case first)
  8. Stage 5: Structure builder (static sections only)  ← Stage 4 (AI) intentionally skipped; pipeline passes ProcessedContent with no-op AI through to Stage 5
  9. Stage 6: EPUB exporter (basic, no template)
  10. Pipeline orchestrator wiring S1→S2→S3→[S4 no-op]→S5→S6

Phase C — Protected Blocks
  11. Equation detector (Stage 2 add-on)
  12. Table standardizer (Stage 2 add-on)
  13. Rewriter placeholder extract/restore (rewriter.py infrastructure)

Phase D — All Ingesters
  14. Markdown ingester
  15. TXT ingester
  16. DOCX ingester
  17. PDF ingester (digital path only)
  18. EPUB ingester
  19. OCR ingester + Tesseract engine
  20. PDF scanned-vs-digital detection

Phase E — All Exporters
  21. DOCX exporter (+ table borders + headers/footers)
  22. PDF exporter (WeasyPrint)
  23. Equation renderer (image path for MVP)
  24. Calibre polish (optional, guarded)

Phase F — AI Stage
  25. AI provider interface + Anthropic implementation
  26. Prompt loader
  27. Title / preface / acknowledgement generators
  28. Content rewriter (chunked, structure-preserving)

Phase G — Metadata + Batch
  29. Excel metadata reader + column mapping
  30. Metadata validator + author credential stripper
  31. Assembler multi-file ordering (expand Phase B single-file case)

Phase H — Template System
  32. Template loader (config.yaml + CSS + Jinja)
  33. Template engine (apply to EPUB/DOCX/PDF exporters)
  34. Academic + Modern template files

Phase I — Job Infrastructure
  35. Job model + file-based store
  36. Subprocess worker
  37. Job manager

Phase J — API + UI
  38. FastAPI routes (jobs + batches + config + health)
  39. Request/response schemas
  40. Simple HTML/JS UI

Phase K — Polish
  41. Full test suite
  42. OpenAI provider (second AI backend)
  43. Documentation (SETUP.md, CONFIGURATION.md, TEMPLATES.md)
```

Each Phase builds on the previous and produces something testable. Don't skip phases.

---

## 3. Phase A — Foundation

### 3.1 Project Scaffold

```
bookforge/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── .env.example
├── config/
│   ├── default.yaml
│   ├── columns.yaml
│   └── prompts/
├── templates/
├── bookforge/
│   ├── __init__.py
│   └── core/
│       ├── __init__.py
│       ├── models.py
│       ├── exceptions.py
│       ├── config.py
│       ├── registry.py
│       └── logging.py
└── tests/
    └── conftest.py
```

**`pyproject.toml` — core dependencies:**

```toml
[project]
name = "bookforge"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "openpyxl>=3.1.0",
    "anthropic>=0.25.0",
    "openai>=1.30.0",
    "pytesseract>=0.3.10",
    "pymupdf>=1.24.0",           # fitz
    "pypandoc>=1.13",
    "python-docx>=1.1.0",
    "ebooklib>=0.18",
    "weasyprint>=62.0",
    "beautifulsoup4>=4.12.0",
    "lxml>=5.0.0",
    "Pillow>=10.0.0",
    "matplotlib>=3.8.0",         # equation image rendering
    "tiktoken>=0.7.0",           # token counting
    "Jinja2>=3.1.0",
    "typer>=0.12.0",
    "structlog>=24.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "httpx>=0.27.0",             # FastAPI test client
    "ruff>=0.4.0",
]
```

### 3.2 Config Loader (`core/config.py`)

Four-layer merge: `default.yaml` → `local.yaml` (git-ignored) → env vars → job-level overrides.

```python
class Config:
    """Immutable merged config. Constructed once at startup."""
    
    @classmethod
    def load(cls, job_overrides: dict | None = None) -> "Config":
        """Load and merge all config layers.
        
        Layer order: default → local → env → job
        """
        base = load_yaml("config/default.yaml")
        local = load_yaml("config/local.yaml", required=False)
        env = extract_env_vars(prefix="BOOKFORGE_")
        return cls._merge(base, local, env, job_overrides or {})
```

Key env vars to support:
```
BOOKFORGE_AI_API_KEY          # Anthropic or OpenAI key
BOOKFORGE_AI_PROVIDER         # "anthropic" | "openai"
BOOKFORGE_DATA_DIR            # Override data/ directory
BOOKFORGE_LOG_LEVEL           # DEBUG | INFO | WARNING
```

### 3.3 Core Models (`core/models.py`)

Implement all `@dataclass` types exactly as specified in ARCHITECTURE.md §4:
- `RawContent`, `NormalizedContent`, `AssembledBook`, `ProcessedContent`
- `BookSection`, `BookManifest`, `BookMetadata`
- `Asset`, `Heading`, `ProtectedBlock`
- `SectionRole` enum, `ProtectedBlockType` enum

**Critical:** `Asset` must be **file-backed** (a `Path` reference), never bytes in memory. This prevents OOM on batches with many large images.

```python
@dataclass
class Asset:
    filename: str
    media_type: str
    file_path: Path          # disk ref — NOT bytes
    size_bytes: int
```

### 3.4 Typed Exceptions (`core/exceptions.py`)

One exception class per pipeline stage. The worker catches at the file boundary.

```python
class BookForgeError(Exception):
    """Base exception."""

class IngestionError(BookForgeError): pass
class NormalizationError(BookForgeError): pass
class AssemblyError(BookForgeError): pass
class AIError(BookForgeError): pass
class StructureError(BookForgeError): pass
class ExportError(BookForgeError): pass
class MetadataError(BookForgeError): pass
class TemplateError(BookForgeError): pass
class ConfigError(BookForgeError): pass
```

### 3.5 Plugin Registry (`core/registry.py`)

Components register at import time via decorators. The pipeline resolves them by name from config.

```python
_ingesters: dict[str, type[BaseIngester]] = {}
_ocr_engines: dict[str, type[BaseOCREngine]] = {}
_ai_providers: dict[str, type[BaseAIProvider]] = {}
_exporters: dict[str, type[BaseExporter]] = {}

def register_ingester(name: str):
    def decorator(cls):
        _ingesters[name] = cls
        return cls
    return decorator

def get_ingester_for_file(file_path: Path) -> BaseIngester:
    """Detect format and return the right ingester instance."""
    format_name = detect_format(file_path)
    cls = _ingesters.get(format_name)
    if not cls:
        raise IngestionError(f"No ingester for format: {format_name}")
    return cls()
```

---

## 4. Phase B — First Pipeline Path

Goal: a single HTML file produces a valid EPUB. No AI, no templates. Proves the stage contract works end to end.

### 4.1 HTML Ingester (`ingestion/html_ingester.py`)

```python
@register_ingester("html")
class HtmlIngester(BaseIngester):
    supported_extensions = [".html", ".htm"]
    supported_mimetypes = ["text/html"]
    
    def can_handle(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.supported_extensions
    
    def ingest(self, file_path: Path, config: dict) -> RawContent:
        """Read HTML file and return RawContent.
        
        - Read file with charset detection (chardet if encoding unknown)
        - Extract embedded images as Assets (write to temp dir, not memory)
        - Return raw HTML as text — normalization happens in Stage 2
        """
```

**Key principle:** Ingesters extract content, they do not clean or structure it. Cleaning is Stage 2's job.

### 4.2 Normalizer (`normalization/normalizer.py`)

The normalizer is the most important stage. It produces the Intermediate Representation that all downstream stages consume.

**Processing order within Stage 2 (must be sequential):**

```
1. html_cleaner.py    — strip scripts/nav/ads, fix broken HTML
2. structure_detector.py — detect headings, wrap in <article>
3. equation_detector.py  — detect LaTeX/MathML, tag as bf-protected
4. table_standardizer.py — normalize tables, tag as bf-protected
```

**HTML Cleaner — what to strip:**

```python
STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "button"]
STRIP_ATTRS = ["onclick", "onload", "class", "id", "style"]  # except bf-* classes
KEEP_ATTRS = {
    "a": ["href"],
    "img": ["src", "alt"],
    "table": [],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
}
```

**Protected block tagging:**

```python
# Equation: LaTeX inline
# Before: <span>The formula $E = mc^2$ is famous.</span>
# After:  <span>The formula <span class="bf-protected" data-type="equation" 
#               data-block-id="PROTECTED_0">$E = mc^2$</span> is famous.</span>

# Table: any <table> element
# Before: <table>...</table>
# After:  <table class="bf-protected" data-type="table" data-block-id="PROTECTED_1">...</table>
```

**What `NormalizedContent.body_html` looks like:**

```html
<article data-source="chapter-1.html">
  <h1>Introduction</h1>
  <p>First paragraph. The formula 
     <span class="bf-protected" data-type="equation" data-block-id="PROTECTED_0">
       $E = mc^2$
     </span> describes mass-energy equivalence.
  </p>
  <table class="bf-protected" data-type="table" data-block-id="PROTECTED_1">
    <thead><tr><th>A</th><th>B</th></tr></thead>
    <tbody><tr><td>1</td><td>2</td></tr></tbody>
  </table>
</article>
```

### 4.3 Assembler — Single File Case (`assembly/assembler.py`)

For Phase B, only handle the single-file case. Multi-file ordering comes in Phase G.

```python
def assemble(articles: list[NormalizedContent], 
             metadata: BookMetadata) -> AssembledBook:
    """Merge articles into one book. Single-file for Phase B."""
    # Wrap each article in <section class="bf-chapter" data-source="...">
    # Promote detected_title to <h1> if not already present
    # Concatenate all chapter HTML into body_html
    # Aggregate all article_titles[], chapter_headings[], protected_blocks[], assets[]
    # Renumber protected block IDs to be unique across all articles
```

Protected block renumbering must happen here — block IDs from separate articles can collide (both start at `PROTECTED_0`). After assembly they must be globally unique.

### 4.4 Structure Builder (`structure/builder.py`)

For Phase B: build manifest with static sections only (no AI-generated content yet).

```python
def build_manifest(content: ProcessedContent, metadata: BookMetadata,
                   config: JobConfig) -> BookManifest:
    sections = []
    sections.append(BookSection(role=SectionRole.COVER, ...))
    sections.append(BookSection(role=SectionRole.TITLE_PAGE, ...))
    sections.append(BookSection(role=SectionRole.COPYRIGHT, ...))
    # Preface/Ack: skip if not generated (Phase B: always skip)
    sections.append(BookSection(role=SectionRole.TABLE_OF_CONTENTS, ...))
    for chapter in split_chapters(content.body_html):
        sections.append(BookSection(role=SectionRole.CHAPTER, ...))
    return BookManifest(sections=sections, metadata=metadata, assets=content.assets)
```

`split_chapters()`: split `body_html` at `<section class="bf-chapter">` boundaries.

### 4.5 EPUB Exporter (`export/epub_exporter.py`)

Build the EPUB package using `ebooklib`. Template integration comes later in Phase H.

```python
@register_exporter("epub")
class EpubExporter(BaseExporter):
    output_format = "epub"
    
    def export(self, manifest: BookManifest, template: Template | None,
               output_path: Path) -> ExportResult:
        book = epub.EpubBook()
        
        # Set metadata
        book.set_identifier(manifest.metadata.eisbn or str(uuid4()))
        book.set_title(manifest.metadata.title)
        book.set_language(manifest.metadata.language)
        book.add_author(", ".join(manifest.metadata.authors))
        
        # Add CSS (basic for Phase B; from template in Phase H)
        book.add_item(epub.EpubItem(uid="style", file_name="style.css",
                                    media_type="text/css", content=CSS))
        
        # Add chapters
        chapters = []
        for section in manifest.sections:
            if section.role == SectionRole.CHAPTER:
                c = epub.EpubHtml(title=section.title, 
                                  file_name=f"chapter_{section.order}.xhtml",
                                  content=section.content_html)
                c.add_item(book.get_item_with_id("style"))
                book.add_item(c)
                chapters.append(c)
        
        # Add front matter sections
        # Spine + TOC
        book.spine = chapters
        book.toc = [(epub.Section(c.title), [c]) for c in chapters]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        
        # Add assets (images)
        for asset in manifest.assets:
            book.add_item(epub.EpubItem(file_name=asset.filename,
                                        media_type=asset.media_type,
                                        content=asset.file_path.read_bytes()))
        
        epub.write_epub(output_path, book)
        return ExportResult(format="epub", output_path=output_path, success=True)
    
    def validate(self, output_path: Path) -> ValidationResult:
        """Run epubcheck if installed."""
        # subprocess call to epubcheck jar — skip silently if not installed
```

### 4.6 Pipeline Orchestrator (`core/pipeline.py`)

Wire stages together. This is the core orchestration code.

```python
class Pipeline:
    
    async def process_file(self, file_path: Path, 
                           config: JobConfig) -> NormalizedContent:
        """Stages 1+2: per-file processing."""
        ingester = registry.get_ingester_for_file(file_path)
        raw = ingester.ingest(file_path, config)
        normalizer = Normalizer(config)
        return normalizer.normalize(raw)
    
    async def process_book(self, normalized_contents: list[NormalizedContent],
                           metadata: BookMetadata, 
                           config: JobConfig) -> list[Path]:
        """Stages 3-6: per-book processing."""
        
        # Stage 3: Assemble
        assembled = assembler.assemble(normalized_contents, metadata)
        
        # Stage 4: AI (may be skipped entirely)
        processed = await ai_stage.process(assembled, config)
        
        # Stage 5: Structure
        manifest = structure_builder.build_manifest(processed, metadata, config)
        
        # Stage 6: Export (parallel for multiple formats)
        template = template_loader.load(config.template)
        outputs = await asyncio.gather(*[
            exporter.export(manifest, template, output_path)
            for fmt, exporter, output_path in get_exporters(config, manifest)
        ])
        
        return [r.output_path for r in outputs if r.success]
```

**Test at end of Phase B:**
```python
def test_html_to_epub():
    """End-to-end: single HTML file → valid EPUB with chapter content."""
    pipeline = Pipeline()
    normalized = [await pipeline.process_file(Path("samples/input/test.html"), config)]
    metadata = BookMetadata(title="Test Book", authors=["Test Author"], ...)
    outputs = await pipeline.process_book(normalized, metadata, config)
    assert outputs[0].suffix == ".epub"
    assert outputs[0].exists()
    # Open with ebooklib, check chapter count, check content
```

---

## 5. Phase C — Protected Blocks

Protected blocks are the mechanism that keeps equations and tables intact through AI rewriting. Implement them before AI (Phase F) so you can test isolation.

### 5.1 Equation Detector (`normalization/equation_detector.py`)

Detect three equation source types:

| Type | Pattern | Example |
|---|---|---|
| LaTeX inline | `$...$` (not `$$`) | `$E = mc^2$` |
| LaTeX display | `$$...$$` or `\begin{equation}...\end{equation}` | `$$\int_0^\infty f(x)dx$$` |
| MathML | `<math ...>...</math>` | `<math><mi>E</mi>...</math>` |
| Image equation | `<img>` inside `<span class="math">` or with alt text starting with `\` | (from DOCX/PDF) |

**Detection order matters:** Run MathML detection first (it's structural, harder to false-positive), then LaTeX.

**Regex trap:** LaTeX `$` signs are ambiguous — a dollar amount like `$5.00` looks like an inline equation start. Use the heuristic: LaTeX equations don't contain spaces at the very start/end of the `$....$` pair.

```python
LATEX_INLINE_PATTERN = re.compile(
    r'(?<!\$)\$(?!\s)(.+?)(?<!\s)\$(?!\$)',
    re.DOTALL
)
```

### 5.2 Protected Block Extraction/Restoration (`ai/rewriter.py`)

The extract→placeholder→restore cycle is critical. Implement it before the AI calls.

```python
def extract_protected_blocks(html: str) -> tuple[str, dict[str, str]]:
    """Replace bf-protected elements with <<<PROTECTED_N>>> placeholders.
    
    Returns: (cleaned_html, {placeholder: original_html})
    """
    placeholders = {}
    soup = BeautifulSoup(html, "lxml")
    
    for i, el in enumerate(soup.find_all(class_="bf-protected")):
        key = f"<<<PROTECTED_{i}>>>"
        placeholders[key] = str(el)
        el.replace_with(key)
    
    return str(soup), placeholders

def restore_protected_blocks(rewritten: str, placeholders: dict[str, str]) -> str:
    """Restore original protected content from placeholders."""
    for key, original in placeholders.items():
        rewritten = rewritten.replace(key, original)
    return rewritten
```

**Test this in isolation** before connecting to AI. Feed known HTML with equations, extract, verify placeholders are correct, restore, verify round-trip is lossless.

---

## 6. Phase D — All Ingesters

### 6.1 Markdown Ingester

Use Pandoc with `--from gfm` (GitHub-Flavored Markdown). This handles tables, fenced code blocks, and task lists automatically.

```python
def ingest(self, file_path: Path, config: dict) -> RawContent:
    html = pypandoc.convert_file(
        str(file_path),
        to="html",
        format="gfm",
        extra_args=["--standalone=false"]
    )
    return RawContent(text=html, format_hint="html", ...)
```

GFM via Pandoc produces well-formed HTML — normalizer Stage 2 receives HTML regardless of input format. This is the key design decision: ingesters output raw content, normalizer always gets HTML.

### 6.2 TXT Ingester

The TXT ingester applies heuristic structure detection before producing `RawContent`:

1. Split on blank lines → paragraphs
2. Detect chapter headings:
   - `Chapter 1`, `CHAPTER ONE`, `Chapter IV` (regex)
   - ALL-CAPS lines ≥ 4 words as potential headings
   - Lines matching `---`, `***`, `===` (separator → section break)
3. Wrap detected headings in `<h1>` / `<h2>`
4. Wrap paragraphs in `<p>`
5. If zero headings detected AND `config.pipeline.txt_ai_structure: true`, delegate to AI for structure inference

**Important:** If AI structure inference is used, it only generates structural HTML (heading/paragraph tags) — never rewrites content.

### 6.3 DOCX Ingester

Use `python-docx` to read, then convert to HTML. Do NOT use Pandoc directly for ingestion — Pandoc loses fine-grained control. Use python-docx to inspect style names and extract tables cleanly.

```python
def ingest(self, file_path: Path, config: dict) -> RawContent:
    doc = Document(file_path)
    html_parts = []
    assets = []
    
    for block in doc.element.body:
        if is_paragraph(block):
            html_parts.append(render_paragraph(block, doc.styles))
        elif is_table(block):
            html_parts.append(render_table(block))
        elif is_image(block):
            asset = extract_image(block, config.temp_dir)
            assets.append(asset)
            html_parts.append(f'<figure><img src="{asset.filename}" /></figure>')
    
    return RawContent(text="\n".join(html_parts), format_hint="html", assets=assets, ...)
```

Preserve these DOCX style names as semantic HTML: `Heading 1` → `<h1>`, `Heading 2` → `<h2>`, `Normal` → `<p>`, `Caption` → `<figcaption>`, `Code` → `<code>`.

### 6.4 PDF Ingester — Digital vs Scanned Detection

Auto-detect on first `n` pages:

```python
def detect_pdf_type(pdf_path: Path, sample_pages: int = 3) -> str:
    """Return "digital" or "scanned"."""
    doc = fitz.open(pdf_path)
    total_chars = 0
    
    for page_num in range(min(sample_pages, len(doc))):
        page = doc[page_num]
        text = page.get_text("text")
        total_chars += len(text.strip())
    
    # Heuristic: if average chars per page < 100, treat as scanned
    avg_chars = total_chars / min(sample_pages, len(doc))
    return "digital" if avg_chars >= 100 else "scanned"
```

For digital PDFs, use `PyMuPDF` (`fitz`) to extract text with layout:
```python
page.get_text("html")   # Preserves basic formatting
```

For scanned PDFs, delegate to OCR ingester:
```python
if pdf_type == "scanned":
    return self.ocr_engine.ocr_pdf(pdf_path, config.ocr.language)
```

### 6.5 EPUB Ingester (Reverse Conversion)

For EPUB → DOCX/PDF workflow. Use `ebooklib` to read the EPUB:

```python
def ingest(self, file_path: Path, config: dict) -> RawContent:
    book = epub.read_epub(str(file_path))
    chapters_html = []
    assets = []
    
    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            chapters_html.append(item.get_content().decode("utf-8"))
        elif item.get_type() == ebooklib.ITEM_IMAGE:
            asset = save_asset_to_disk(item, config.temp_dir)
            assets.append(asset)
    
    return RawContent(text="\n".join(chapters_html), format_hint="html", assets=assets, ...)
```

### 6.6 OCR Ingester + Tesseract

```python
@register_ocr_engine("tesseract")
class TesseractOCREngine(BaseOCREngine):
    
    def ocr_image(self, image_path: Path, language: str) -> str:
        img = Image.open(image_path)
        # Pre-process: convert to grayscale, apply threshold for better accuracy
        img = img.convert("L")
        psm = config.get("ocr.page_segmentation_mode", 6)   # default 6 = uniform block of text
        text = pytesseract.image_to_string(img, lang=language, config=f"--psm {psm}")
        return text
    
    def ocr_pdf(self, pdf_path: Path, language: str) -> list[PageResult]:
        doc = fitz.open(pdf_path)
        results = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300)
            img_path = save_page_image(pix, page_num)
            text = self.ocr_image(img_path, language)
            results.append(PageResult(page_num=page_num, text=text))
        return results
```

**OCR concurrency:** OCR is CPU-bound. Use `asyncio.Semaphore(config.ocr.max_concurrent_pages)` to avoid saturating CPU.

**Known limitation (documented in SETUP.md):** Tesseract cannot reconstruct equations from scans. LaTeX/mathematical notation becomes garbled text. Refer clients with math-heavy scanned content to use digital source files or Mathpix pre-processing.

---

## 7. Phase E — All Exporters

### 7.1 DOCX Exporter

Three distinct responsibilities:
1. Build DOCX document structure via `python-docx`
2. Apply hairline grid borders to all tables
3. Apply headers/footers with page numbers

**Table borders** (mandatory client requirement):

```python
def _apply_table_borders(self, doc: Document, template_config: dict):
    """Apply hairline grid borders to every table.
    
    Uses low-level XML manipulation — python-docx has no high-level 
    border API. Border size "2" = 0.25pt (1/8th point unit).
    """
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    
    def set_cell_border(cell, **kwargs):
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        tcBorders = OxmlElement('w:tcBorders')
        for edge in ('top', 'bottom', 'start', 'end', 'insideH', 'insideV'):
            border = OxmlElement(f'w:{edge}')
            border.set(qn('w:val'), kwargs.get('val', 'single'))
            border.set(qn('w:sz'), str(kwargs.get('sz', 2)))   # 0.25pt
            border.set(qn('w:space'), '0')
            border.set(qn('w:color'), '000000')
            tcBorders.append(border)
        tcPr.append(tcBorders)
    
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                set_cell_border(cell, val="single", sz=2)
```

**Page numbers in footer:**

```python
def _add_page_number(self, paragraph):
    """Add PAGE field code to paragraph for auto page numbers."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    
    run = paragraph.add_run()
    fldChar = OxmlElement('w:fldChar')
    fldChar.set(qn('w:fldCharType'), 'begin')
    run._r.append(fldChar)
    
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = ' PAGE '
    run._r.append(instrText)
    
    fldChar = OxmlElement('w:fldChar')
    fldChar.set(qn('w:fldCharType'), 'end')
    run._r.append(fldChar)
```

### 7.2 PDF Exporter (WeasyPrint)

```python
@register_exporter("pdf")
class PdfExporter(BaseExporter):
    output_format = "pdf"
    
    def export(self, manifest: BookManifest, template: Template | None,
               output_path: Path) -> ExportResult:
        # Assemble full HTML document from all sections
        html_content = self._render_full_html(manifest, template)
        
        # Pre-process equations: render to images for PDF
        html_content = equation_renderer.render_for_pdf(html_content, manifest.assets)
        
        # Apply CSS from template (styles.css + print.css)
        css_list = []
        if template:
            css_list.append(CSS(filename=str(template.styles_css)))
            css_list.append(CSS(filename=str(template.print_css)))
        
        # Generate PDF
        document = HTML(string=html_content).render(stylesheets=css_list)
        document.write_pdf(output_path)
        
        return ExportResult(format="pdf", output_path=output_path, success=True)
```

**WeasyPrint gotcha:** It does not support external `url()` references for fonts unless you pass `base_url`. Always pass `base_url=str(template.directory)` so `@font-face` can resolve relative font paths.

### 7.3 Equation Renderer (`export/equation_renderer.py`)

MVP: all equations render to PNG images.

```python
def render_equation_to_image(latex_or_mathml: str, dpi: int = 300,
                              output_dir: Path = None) -> Path:
    """Render equation to PNG using matplotlib.mathtext.
    
    Input: LaTeX string (e.g., "$E = mc^2$") or MathML string
    Output: PNG file path
    
    MathML path: convert MathML to LaTeX first using lxml (basic conversion),
    then render via matplotlib. For complex MathML, log a warning and use 
    text fallback.
    """
    import matplotlib
    matplotlib.use("Agg")   # headless rendering
    import matplotlib.pyplot as plt
    import matplotlib.mathtext as mathtext
    
    # Clean up LaTeX delimiters for matplotlib
    latex = extract_latex_content(latex_or_mathml)
    
    fig = plt.figure(figsize=(0.1, 0.1))
    fig.text(0, 0, f"${latex}$", fontsize=12)
    
    # Tight layout to remove whitespace
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", 
                pad_inches=0.02, transparent=True)
    plt.close(fig)
    
    return output_path
```

**matplotlib.mathtext limitation:** It handles most LaTeX math but NOT:
- Multi-line aligned equations (`\begin{align}`)
- `\text{}` with non-ASCII characters
- Fancy spacing commands (`\quad`, `\hspace`)

For these, fall back to rendering the raw LaTeX string as monospace text and log a warning.

### 7.4 Calibre Polish (`export/calibre_polish.py`)

Optional post-processing — skip silently if Calibre not installed.

```python
def calibre_polish_epub(epub_path: Path) -> Path:
    """Run Calibre ebook-polish on the EPUB if Calibre is installed.
    
    Improves cover embedding, metadata normalization, and reader compatibility.
    If Calibre is not installed, return original path unchanged.
    """
    if not shutil.which("ebook-polish"):
        logger.debug("Calibre not installed — skipping EPUB polish")
        return epub_path
    
    output_path = epub_path.with_stem(epub_path.stem + "_polished")
    result = subprocess.run(
        ["ebook-polish", str(epub_path), str(output_path)],
        capture_output=True, timeout=120
    )
    
    if result.returncode == 0:
        return output_path
    else:
        logger.warning("Calibre polish failed, using unpolished EPUB",
                       stderr=result.stderr.decode())
        return epub_path
```

---

## 8. Phase F — AI Stage

### 8.1 AI Provider Interface + Anthropic Implementation

```python
class AnthropicAIProvider(BaseAIProvider):
    
    def __init__(self, config: dict):
        self.client = anthropic.Anthropic(api_key=config.ai.api_key)
        self.model = config.ai.model
        self.max_tokens = config.ai.max_tokens
        self.rate_limiter = RateLimiter(config.ai.rate_limit_rpm)
        self.cost_tracker = CostTracker(config.ai.cost_limit_per_job_usd)
    
    def generate(self, prompt: str, context: str, max_tokens: int) -> str:
        self.rate_limiter.acquire()
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "user", "content": f"{context}\n\n{prompt}"}
            ]
        )
        self.cost_tracker.record(response.usage)
        return response.content[0].text
    
    def rewrite(self, text: str, instruction: str, max_tokens: int,
                system_context: str = "") -> str:
        """Rewrite text per instruction. system_context is read-only context
        from the previous chunk — not included in the text to rewrite."""
        self.rate_limiter.acquire()
        
        system = instruction
        if system_context:
            system += f"\n\nContext from previous section (DO NOT rewrite this, it is for reference only):\n---\n{system_context}\n---"
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[
                {"role": "user", "content": f"---BEGIN REWRITE---\n{text}"}
            ]
        )
        self.cost_tracker.record(response.usage)
        return response.content[0].text
```

**AI error handling (per REQUIREMENTS.md §13):**

```python
def _call_with_retry(self, fn, *args, **kwargs):
    """Retry AI calls 3x with exponential backoff."""
    for attempt in range(3):
        try:
            return fn(*args, **kwargs)
        except anthropic.RateLimitError:
            wait = 2 ** attempt * 5   # 5s, 10s, 20s
            time.sleep(wait)
        except anthropic.APIError as e:
            if attempt == 2:
                raise AIError(f"AI call failed after 3 attempts: {e}") from e
            time.sleep(2 ** attempt)
```

### 8.2 Prompt Loader (`ai/prompt_loader.py`)

Prompts live in `config/prompts/*.txt`. No hardcoded prompt strings in code.

```python
def load_prompt(name: str, config: Config) -> str:
    """Load prompt template from config/prompts/{name}.txt.
    
    Prompts support {variable} placeholders:
    - {article_titles} — comma-separated titles for title generation
    - {word_count_target} — for rewrite expansion/reduction
    - {language} — target language
    """
    prompt_path = Path(config.ai.prompts_dir) / f"{name}.txt"
    if not prompt_path.exists():
        raise ConfigError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")
```

**Default prompts to ship:**

`config/prompts/title.txt`:
```
You are an academic book editor. Generate a concise, scholarly book title 
for a volume containing the following articles:

{article_titles}

Requirements:
- One main title (maximum 10 words)
- Optional subtitle after a colon
- Academic tone
- Do not include the article titles verbatim
- Output only the title, nothing else
```

`config/prompts/rewrite.txt`:
```
You are a professional editor. Rewrite the following text to be {direction} 
by approximately {percent}%.

Rules:
- Preserve all headings and section structure exactly
- Do NOT modify, remove, or paraphrase any content marked <<<PROTECTED_N>>>
- Preserve technical accuracy
- Maintain the author's voice and academic register
- Output only the rewritten text
```

### 8.3 Content Rewriter (`ai/rewriter.py`)

The full chunked rewriter as specified in ARCHITECTURE.md §3 Stage 4:

```python
def rewrite_chapter(chapter_html: str, rewrite_percent: int,
                    ai_provider: BaseAIProvider, config: Config) -> str:
    """Rewrite chapter with protected block preservation and chunk handling."""
    
    direction = "longer" if rewrite_percent > 0 else "shorter"
    percent = abs(rewrite_percent)
    
    # 1. Extract protected blocks
    text, placeholders = extract_protected_blocks(chapter_html)
    
    # 2. Count tokens
    token_count = count_tokens(text, config.ai.model)
    max_chunk = config.ai.max_chunk_tokens   # default 3000
    
    # 3. Build instruction
    prompt_template = prompt_loader.load_prompt("rewrite", config)
    instruction = prompt_template.format(direction=direction, percent=percent)
    
    # 4. Rewrite (single call or chunked)
    if token_count <= max_chunk:
        rewritten = ai_provider.rewrite(text, instruction, config.ai.max_tokens)
    else:
        chunks = split_at_paragraphs(text, max_chunk)
        rewritten_chunks = []
        prev_context = ""
        
        for chunk in chunks:
            rewritten_chunk = ai_provider.rewrite(
                chunk, instruction, config.ai.max_tokens,
                system_context=prev_context
            )
            rewritten_chunks.append(rewritten_chunk)
            prev_context = chunk[-500:]  # original trailing context, not rewritten
        
        rewritten = "\n".join(rewritten_chunks)
    
    # 5. Restore protected blocks
    return restore_protected_blocks(rewritten, placeholders)
```

**`split_at_paragraphs()`:** Split at `<p>` tag boundaries. Never split mid-paragraph. Accumulate paragraphs into a chunk until adding the next would exceed `max_chunk_tokens`. This guarantees each chunk is coherent and never truncates a paragraph.

---

## 9. Phase G — Metadata + Batch

### 9.1 Excel Reader (`metadata/reader.py`)

```python
def read_metadata(excel_path: Path, columns_config: dict) -> list[dict]:
    """Read Excel, apply column mapping, return raw row dicts.
    
    columns_config maps canonical field names to Excel column names:
    e.g., {"author_name": "Author", "isbn": "ISBN Number"}
    """
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb.active
    
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    
    # Build reverse mapping: excel_col_name → canonical_name
    col_map = {v: k for k, v in columns_config.items()}
    
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        row_dict = {}
        for i, value in enumerate(row):
            if i < len(headers) and headers[i] in col_map:
                row_dict[col_map[headers[i]]] = value
        if any(v is not None for v in row_dict.values()):  # skip blank rows
            rows.append(row_dict)
    
    return rows
```

**`config/columns.yaml`** — default column mapping (all remappable):

```yaml
# Maps canonical field names to Excel column headers
# Edit this file to match your Excel sheet without changing any code
mappings:
  title: "Title"
  author_name: "Author"
  isbn: "ISBN"
  eisbn: "eISBN"
  publisher_name: "Publisher"
  publisher_address: "Publisher Address"
  publisher_email: "Publisher Email"
  year: "Year"
  language: "Language"
  input_files: "Input Files"
  template: "Template"
  rewrite_percent: "Rewrite %"
  generate_preface: "Generate Preface"
  generate_acknowledgement: "Generate Acknowledgement"
  output_formats: "Output Formats"
```

### 9.2 Author Credential Stripper (`metadata/validator.py`)

```python
def strip_author_credentials(raw_name: str) -> str:
    """Strip academic/professional credentials from author name.
    
    Client requirement: only first/last name — no degrees, titles, institutions.
    """
    name = raw_name.strip()
    
    # Remove common prefixes
    prefix_pattern = r'^(Dr\.?|Prof\.?|Professor|Mr\.?|Mrs\.?|Ms\.?|Sir|Dame)\s+'
    name = re.sub(prefix_pattern, '', name, flags=re.IGNORECASE)
    
    # Remove parenthetical content: "Name (University of ...)"
    name = re.sub(r'\s*\([^)]*\)', '', name)
    
    # Remove suffixes after comma: "Name, Ph.D., MIT"
    # Split at first comma and take only the name part
    if ',' in name:
        name = name.split(',')[0].strip()
    
    # Remove common suffix patterns still remaining
    suffix_pattern = r'\s+(Ph\.?D\.?|M\.?D\.?|M\.?Sc\.?|B\.?Sc\.?|MBA|FACP|FRCP|FRS)\b'
    name = re.sub(suffix_pattern, '', name, flags=re.IGNORECASE)
    
    name = ' '.join(name.split())  # normalize whitespace
    
    if not name:
        raise MetadataError("Author name is empty after credential stripping")
    
    return name
```

Test cases to include:
- `"Dr. John Smith, Ph.D., MIT"` → `"John Smith"`
- `"Prof. Jane Doe (University of Cambridge)"` → `"Jane Doe"`
- `"A. Kumar, M.D., FACP"` → `"A. Kumar"`
- `"Dr. Sarah O'Brien"` → `"Sarah O'Brien"` (apostrophes preserved)

### 9.3 Assembler — Multi-File Ordering

Expand the Phase B single-file assembler to handle multiple articles:

```python
def _order_articles(articles: list[NormalizedContent], 
                    metadata: BookMetadata) -> list[NormalizedContent]:
    """Order articles per ARCHITECTURE §3 Stage 3 rules.
    
    Priority:
    1. Excel chapter_order column (explicit integer ordering)
    2. Excel row order (positional in sheet — most common case)
    3. Filename alphabetical sort (single-upload without Excel)
    """
    if metadata.chapter_order:
        return sorted(articles, key=lambda a: metadata.chapter_order.get(a.source_path.name, 999))
    elif metadata.source_row_indices:
        return sorted(articles, key=lambda a: metadata.source_row_indices.get(a.source_path.name, 999))
    else:
        return sorted(articles, key=lambda a: a.source_path.name)
```

---

## 10. Phase H — Template System

### 10.1 Template Loader (`templates/loader.py`)

```python
@dataclass
class Template:
    name: str
    directory: Path
    config: TemplateConfig
    styles_css: Path
    print_css: Path
    docx_reference: Path | None
    fonts: list[Path]
    jinja_env: jinja2.Environment   # for copyright.html.jinja, title_page.html.jinja

def load_template(name: str, templates_dir: Path) -> Template:
    """Load template directory into Template object.
    
    Validates at load time:
    - config.yaml exists and is valid
    - styles.css exists
    - print.css exists
    - All fonts in fonts/ directory are readable
    - Jinja templates only reference variables defined in BookMetadata
    """
    template_dir = templates_dir / name
    if not template_dir.is_dir():
        raise TemplateError(f"Template not found: {name}")
    
    config = load_yaml(template_dir / "config.yaml")
    
    # Validate Jinja templates at load time — not at render time
    for jinja_file in template_dir.glob("*.jinja"):
        validate_jinja_variables(jinja_file, allowed_vars=BOOK_METADATA_FIELDS)
    
    return Template(
        name=name,
        directory=template_dir,
        config=TemplateConfig(**config),
        styles_css=template_dir / "styles.css",
        print_css=template_dir / "print.css",
        docx_reference=template_dir / "docx_reference.docx" if (template_dir / "docx_reference.docx").exists() else None,
        fonts=list((template_dir / "fonts").glob("*.ttf")),
        jinja_env=jinja2.Environment(loader=jinja2.FileSystemLoader(str(template_dir)))
    )
```

### 10.2 Academic Template CSS

Key CSS rules for `templates/academic/styles.css`:

```css
/* Fonts */
@font-face {
    font-family: 'Crimson Text';
    src: url('fonts/CrimsonText-Regular.ttf') format('truetype');
}

/* Body */
body {
    font-family: 'Crimson Text', Georgia, serif;
    font-size: 11pt;
    line-height: 1.5;
}

/* Tables — hairline grid borders for EPUB/PDF */
table {
    border-collapse: collapse;
    width: 100%;
}
table th, table td {
    border: 0.25pt solid #000000;
    padding: 4pt 6pt;
}
table thead tr {
    background-color: #f0f0f0;
    font-weight: bold;
}

/* Chapters */
section.bf-chapter {
    page-break-before: always;
}

/* Equations */
span.bf-protected[data-type="equation"] img {
    vertical-align: middle;
}
```

---

## 11. Phase I — Job Infrastructure

### 11.1 Job Model (`jobs/models.py`)

```python
class JobStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class JobProgress:
    total_files: int
    completed_files: int
    current_file: str | None
    current_stage: str | None
    succeeded: int
    failed: int
    elapsed_seconds: float

@dataclass
class FileResult:
    file_path: Path
    status: str          # "success" | "failed" | "skipped"
    error: str | None
    output_paths: list[Path]

@dataclass
class Job:
    job_id: str          # UUID
    status: JobStatus
    input_files: list[Path]
    metadata: BookMetadata
    config: JobConfig
    progress: JobProgress
    file_results: list[FileResult]
    created_at: datetime
    completed_at: datetime | None
    report: BatchReport | None
```

### 11.2 File-Based Store (`jobs/store.py`)

Job state lives entirely on disk at `data/jobs/{job_id}/`. The API reads `status.json` directly for polling. No in-memory state.

```python
class FileJobStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
    
    def write_job(self, job: Job):
        job_dir = self.base_dir / job.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "job.json").write_text(json.dumps(asdict(job), default=str))
    
    def write_status(self, job_id: str, progress: JobProgress):
        """Worker calls this after each file. API reads this for polling."""
        status_path = self.base_dir / job_id / "status.json"
        status_path.write_text(json.dumps(asdict(progress), default=str))
    
    def read_job(self, job_id: str) -> Job | None:
        job_path = self.base_dir / job_id / "job.json"
        if not job_path.exists():
            return None
        return Job(**json.loads(job_path.read_text()))
    
    def read_status(self, job_id: str) -> JobProgress | None:
        status_path = self.base_dir / job_id / "status.json"
        if not status_path.exists():
            return None
        return JobProgress(**json.loads(status_path.read_text()))
```

### 11.3 Subprocess Worker (`jobs/worker.py`)

The worker runs as a subprocess so crashes/restarts don't kill in-progress jobs.

```python
# worker.py — entry point for subprocess
if __name__ == "__main__":
    job_id = sys.argv[1]
    data_dir = Path(sys.argv[2])
    
    store = FileJobStore(data_dir)
    job = store.read_job(job_id)
    
    asyncio.run(run_job(job, store))

async def run_job(job: Job, store: FileJobStore):
    semaphore = asyncio.Semaphore(job.config.max_concurrent_files)
    
    # --- Stages 1+2: per-file (parallel) ---
    # Each file is ingested and normalized independently.
    # Results accumulate into normalized_contents; failed files are recorded and skipped.
    normalized_contents: list[NormalizedContent] = []
    
    async def process_one_file(file_path: Path):
        async with semaphore:
            store.write_status(job.job_id, JobProgress(
                ..., current_file=file_path.name, current_stage="ingesting"
            ))
            try:
                normalized = await pipeline.process_file(file_path, job.config)
                return normalized
            except BookForgeError as e:
                logger.error("File ingestion/normalization failed",
                             file=str(file_path), error=str(e))
                store.write_file_result(job.job_id, FileResult(
                    file_path=file_path, status="failed", error=str(e)
                ))
                return None
    
    results = await asyncio.gather(
        *[process_one_file(f) for f in job.input_files],
        return_exceptions=True
    )
    normalized_contents = [r for r in results if isinstance(r, NormalizedContent)]
    
    if not normalized_contents:
        store.write_status(job.job_id, JobProgress(..., current_stage="failed"))
        return
    
    # --- Stages 3-6: per-book (sequential) ---
    # All successfully normalized articles are assembled into one book,
    # then processed through AI, Structure, and Export as a single unit.
    store.write_status(job.job_id, JobProgress(..., current_stage="assembling"))
    try:
        output_paths = await pipeline.process_book(
            normalized_contents, job.metadata, job.config
        )
        store.write_file_result(job.job_id, FileResult(
            file_path=job.input_files[0],  # book-level result
            status="success",
            output_paths=output_paths
        ))
    except BookForgeError as e:
        logger.error("Book processing failed", error=str(e))
        store.write_status(job.job_id, JobProgress(..., current_stage="failed"))
        return
    
    store.write_status(job.job_id, JobProgress(..., current_stage="completed"))
```

**Spawning from the API:**

```python
def spawn_worker(job_id: str, data_dir: Path):
    subprocess.Popen(
        [sys.executable, "-m", "bookforge.jobs.worker", job_id, str(data_dir)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True   # detach from parent process group
    )
```

`start_new_session=True` is critical — it prevents the worker from dying when the API process restarts or receives SIGINT.

---

## 12. Phase J — API + UI

### 12.1 FastAPI Application (`main.py`)

```python
app = FastAPI(
    title="BookForge",
    version="0.1.0",
    docs_url="/docs",
)

app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "tesseract": bool(shutil.which("tesseract")),
        "calibre": bool(shutil.which("ebook-polish")),
        "pandoc": bool(shutil.which("pandoc")),
    }
```

### 12.2 Job Creation Endpoint

```python
@router.post("/jobs", response_model=JobResponse)
async def create_job(
    files: list[UploadFile] = File(...),
    metadata: str = Form(...),     # JSON string of BookMetadata fields
    config: str = Form(...),       # JSON string of JobConfig fields
):
    """Create a single conversion job.
    
    Files are saved to data/jobs/{job_id}/input/ before spawning worker.
    """
    job_id = str(uuid4())
    job_dir = settings.data_dir / "jobs" / job_id
    input_dir = job_dir / "input"
    input_dir.mkdir(parents=True)
    
    # Save uploaded files to disk
    saved_paths = []
    for upload in files:
        dest = input_dir / upload.filename
        dest.write_bytes(await upload.read())
        saved_paths.append(dest)
    
    # Build Job
    job = Job(
        job_id=job_id,
        status=JobStatus.QUEUED,
        input_files=saved_paths,
        metadata=BookMetadata(**json.loads(metadata)),
        config=JobConfig(**json.loads(config)),
        ...
    )
    
    store.write_job(job)
    spawn_worker(job_id, settings.data_dir)
    
    return JobResponse.from_job(job)
```

### 12.3 Simple UI

The UI is static HTML + vanilla JavaScript. No framework. It polls `GET /api/v1/jobs/{id}` every 2 seconds to show progress.

```html
<!-- bookforge/ui/static/index.html -->
<!DOCTYPE html>
<html>
<head>
    <title>BookForge</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <h1>BookForge</h1>
    
    <!-- Upload section -->
    <section id="upload">
        <h2>New Job</h2>
        <form id="upload-form" enctype="multipart/form-data">
            <input type="file" name="files" multiple accept=".html,.md,.txt,.docx,.pdf,.epub,.tiff,.png,.jpg,.bmp">
            <div id="options">
                <label>Template:
                    <select name="template">
                        <option value="academic">Academic</option>
                        <option value="modern">Modern</option>
                    </select>
                </label>
                <label>Rewrite %: <input type="number" name="rewrite_percent" value="0" min="-80" max="100"></label>
                <label>Output formats: 
                    <select name="output_formats" multiple>
                        <option value="epub" selected>EPUB</option>
                        <option value="docx">DOCX</option>
                        <option value="pdf">PDF</option>
                    </select>
                </label>
            </div>
            <button type="submit">Start Job</button>
        </form>
    </section>
    
    <!-- Jobs list -->
    <section id="jobs">
        <h2>Jobs</h2>
        <div id="jobs-list"></div>
    </section>
    
    <script src="/static/app.js"></script>
</body>
</html>
```

---

## 13. Phase K — Testing

### 13.1 Test Structure

```
tests/
├── conftest.py                      # Fixtures: temp dirs, sample files, mock AI
├── test_ingestion/
│   ├── test_html_ingester.py
│   ├── test_markdown_ingester.py
│   ├── test_txt_ingester.py
│   ├── test_docx_ingester.py
│   ├── test_pdf_ingester.py
│   ├── test_epub_ingester.py
│   └── test_ocr_ingester.py
├── test_normalization/
│   ├── test_html_cleaner.py
│   ├── test_equation_detector.py
│   ├── test_table_standardizer.py
│   └── test_protected_blocks.py    # Extract/restore round-trip
├── test_assembly/
│   ├── test_single_file.py
│   ├── test_multi_file_ordering.py
│   └── test_deduplicator.py
├── test_ai/
│   ├── test_rewriter.py            # Mock AI provider
│   ├── test_generators.py          # Mock AI provider
│   └── test_chunking.py            # Long chapter chunking logic
├── test_export/
│   ├── test_epub_exporter.py
│   ├── test_docx_exporter.py       # Including table borders
│   ├── test_pdf_exporter.py
│   └── test_equation_renderer.py
├── test_metadata/
│   ├── test_reader.py
│   ├── test_validator.py
│   └── test_author_stripper.py
├── test_templates/
│   └── test_template_loader.py
└── test_integration/
    ├── test_html_to_epub.py
    ├── test_markdown_to_epub.py
    ├── test_txt_to_epub.py
    ├── test_docx_to_epub.py
    ├── test_pdf_to_epub.py
    ├── test_epub_to_docx.py
    ├── test_all_formats_to_all_outputs.py
    └── test_batch_50_files.py
```

### 13.2 AI Test Strategy

Never call the real AI API in tests. Use a mock provider:

```python
# conftest.py
@pytest.fixture
def mock_ai_provider():
    """Mock AI provider that returns deterministic responses."""
    class MockAIProvider(BaseAIProvider):
        def generate(self, prompt, context, max_tokens):
            return "Mock Generated Title: Test Book on Testing"
        def rewrite(self, text, instruction, max_tokens, system_context=""):
            # Return slightly modified text (add one word) to prove it ran
            return text + " [rewritten]"
    return MockAIProvider()
```

For rewriter tests specifically, test the chunking logic with a mock that records call count and input sizes — verify that a 10,000-token chapter produces multiple calls with no call exceeding `max_chunk_tokens`.

### 13.3 Critical Tests (must pass before ship)

Per REQUIREMENTS.md §21 success criteria:

```python
# test_integration/test_success_criteria.py

def test_all_input_formats_produce_epub():
    """Criterion 1: All 7 input formats → EPUB."""
    for format_name, sample_file in SAMPLE_FILES.items():
        result = run_pipeline(sample_file, output_formats=["epub"])
        assert result.success, f"{format_name} failed: {result.error}"
        assert result.output_paths[0].suffix == ".epub"

def test_epub_docx_pdf_pass_validation():
    """Criterion 2: All output formats pass validation."""
    result = run_pipeline(SAMPLE_HTML, output_formats=["epub", "docx", "pdf"])
    assert validate_epub(result.epub_path).valid
    assert validate_docx(result.docx_path).opens_in_word
    assert validate_pdf(result.pdf_path).is_valid

def test_tables_render_with_grid_borders():
    """Criterion 5: Tables have hairline grid borders in all formats."""
    result = run_pipeline(HTML_WITH_TABLE, output_formats=["epub", "docx", "pdf"])
    assert epub_table_has_borders(result.epub_path)
    assert docx_table_has_borders(result.docx_path)
    # PDF: visual check only — inspect CSS output

def test_batch_50_files_no_crash():
    """Criterion 8: 50-file batch completes without crashing."""
    files = [generate_sample_html(f"Article {i}") for i in range(50)]
    result = run_batch(files)
    assert result.failed_count == 0
    assert result.succeeded_count == 50
```

---

## 14. Known Implementation Traps

These are the non-obvious places where implementation commonly fails:

### 14.1 Asset Memory Management

**Wrong:**
```python
@dataclass
class Asset:
    data: bytes   # ← crashes on 100MB PDFs with many images
```

**Right:**
```python
@dataclass
class Asset:
    file_path: Path   # ← always on disk
```

Write asset bytes to temp dir immediately on extraction. Never hold image data in memory across pipeline stages.

### 14.2 Protected Block ID Collisions

When assembling multiple articles, `PROTECTED_0` from article 1 and `PROTECTED_0` from article 2 are different. Renumber immediately in the assembler, before AI stage.

```python
def _renumber_protected_blocks(articles: list[NormalizedContent]) -> list[NormalizedContent]:
    """Give globally unique IDs to all protected blocks across all articles."""
    counter = 0
    result = []
    for article in articles:
        renamed_blocks = []
        html = article.body_html
        for block in article.protected_blocks:
            old_id = block.block_id
            new_id = f"PROTECTED_{counter}"
            html = html.replace(old_id, new_id)
            renamed_blocks.append(replace(block, block_id=new_id))
            counter += 1
        result.append(replace(article, body_html=html, protected_blocks=renamed_blocks))
    return result
```

### 14.3 Rewriter Duplicate Content

When chunking, do NOT pass the end of the previous rewritten chunk as context for the next chunk. Pass the end of the **original** chunk instead:

```python
prev_context = chunk[-500:]   # original, NOT rewritten_chunk[-500:]
```

If you pass `rewritten_chunk[-500:]`, the AI may try to "continue" the rewrite of that context instead of using it as reference only, producing duplicate content at chunk boundaries.

### 14.4 DOCX Table Borders vs Reference Doc

`docx_reference.docx` sets default table styles. But python-docx's table border API often doesn't override them reliably. Always call `_apply_table_borders()` explicitly after Pandoc conversion — do not rely on the reference doc for borders.

### 14.5 WeasyPrint Font Resolution

WeasyPrint resolves `url()` relative to `base_url`. If `base_url` is not set, `@font-face` font files will 404 silently and WeasyPrint falls back to system fonts without warning.

```python
HTML(string=html_content, base_url=str(template.directory)).render(...)
```

### 14.6 Tesseract Equation Garbage

Do not try to fix OCR equation output. Tesseract produces garbage for math symbols. The correct behavior is:

1. OCR runs on the full page as-is
2. The garbage text ends up in `RawContent.text`
3. Stage 2 equation detector finds NO equations (because it's not LaTeX syntax)
4. The garbage text passes through to output

This is the documented known limitation. Do not add post-processing to "detect and remove" OCR equation garbage — that heuristic will sometimes remove valid content.

### 14.7 Subprocess Worker `start_new_session`

Without `start_new_session=True`, pressing Ctrl+C on the API server will send SIGINT to the worker subprocess and kill it mid-job. Always detach workers.

### 14.8 Calibre Binary Name on macOS

On macOS, Calibre CLI tools are not on `PATH` by default. They live in `/Applications/calibre.app/Contents/MacOS/`. Check both:

```python
def find_calibre_binary(name: str) -> str | None:
    if shutil.which(name):
        return name
    macos_path = f"/Applications/calibre.app/Contents/MacOS/{name}"
    if Path(macos_path).exists():
        return macos_path
    return None
```

---

## 15. Configuration Reference (Dev Setup)

`.env.example`:
```
BOOKFORGE_AI_API_KEY=your-anthropic-or-openai-key
BOOKFORGE_AI_PROVIDER=anthropic
BOOKFORGE_DATA_DIR=data
BOOKFORGE_LOG_LEVEL=INFO
```

`config/local.yaml` (git-ignored, for local overrides):
```yaml
ai:
  api_key: "${BOOKFORGE_AI_API_KEY}"

ocr:
  page_segmentation_mode: 6   # 6=uniform block, 3=fully automatic, 11=sparse text

pipeline:
  temp_dir: "/tmp/bookforge"
```

**First-run checklist:**
```bash
# Install system dependencies
brew install tesseract pandoc

# Install Python dependencies
pip install -e ".[dev]"

# Copy env
cp .env.example config/local.yaml

# Run tests (no AI calls — mocked)
pytest tests/ -v --ignore=tests/test_integration

# Run integration tests (requires real API key)
BOOKFORGE_AI_API_KEY=your-key pytest tests/test_integration -v

# Start dev server
uvicorn bookforge.main:app --reload --port 8000
```

---

## 16. MVP Completion Checklist

- [x] All 7 ingesters implemented and tested
- [x] Normalizer with protected blocks (equations, tables, captions)
- [x] Assembler (single + multi-file with ordering)
- [x] AI stage: title, preface, ack generators + content rewriter
- [x] EPUB exporter + epubcheck validation
- [x] DOCX exporter + table borders + headers/footers
- [x] PDF exporter (WeasyPrint) + equation image rendering
- [x] Calibre polish (optional, guarded)
- [x] Excel metadata reader + column mapping
- [x] Author credential stripper
- [x] Template system with Academic + Modern templates
- [x] `docs/TEMPLATES.md` with all Jinja variables documented (ship-blocking)
- [x] File-based job store + subprocess worker
- [x] FastAPI REST API (all endpoints in §11)
- [x] Simple web UI with upload + job list + download
- [x] Full test suite passing
- [x] Docker + docker-compose working
- [x] SETUP.md documenting OCR equation limitation
```
