# BookForge — Architecture Design

**Version:** 1.0
**Date:** 2026-04-05
**Status:** Draft

---

## 1. Design Philosophy

Three principles drive every architectural decision:

1. **Pipeline as a sequence of pure transforms** — each stage takes input, produces output, has no side effects on other stages
2. **Content and styling are completely separate** — the pipeline produces structured content; templates apply visual styling at the very end
3. **Every pluggable component shares one interface** — swap OCR engines, AI providers, or export formats without touching the pipeline

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            BookForge System                                   │
│                                                                               │
│  ┌──────────┐    ┌───────────────────────────────────────────────────┐       │
│  │  REST API │───▶│                  JOB MANAGER                     │       │
│  │ (FastAPI) │    │  Creates jobs, tracks status, manages queue      │       │
│  └──────────┘    └───────────────────┬───────────────────────────────┘       │
│  ┌──────────┐                        │                                       │
│  │ Web UI   │────────────────────────┘                                       │
│  │ (static) │                                                                │
│  └──────────┘                        ▼                                       │
│                    ┌─────────────────────────────────┐                       │
│                    │        PIPELINE ENGINE           │                       │
│                    │   Orchestrates the 6 stages      │                       │
│                    └──────────┬──────────────────────┘                       │
│                               │                                              │
│    ┌─────────┬────────┬───────┼────────┬──────────┬─────────┐               │
│    ▼         ▼        ▼       ▼        ▼          ▼         ▼               │
│ ┌───────┐┌───────┐┌───────┐┌──────┐┌──────────┐┌────────┐                 │
│ │STAGE 1││STAGE 2││STAGE 3││STAGE4││ STAGE 5  ││STAGE 6 │                 │
│ │Ingest ││Normal-││Assem- ││  AI  ││Structure ││ Export │                 │
│ │       ││ize    ││ble    ││      ││          ││        │                 │
│ └───┬───┘└───┬───┘└───┬───┘└──┬───┘└────┬─────┘└───┬────┘                 │
│     │        │        │       │         │          │                        │
│ ┌───┴───┐    │        │  ┌────┴───┐     │     ┌────┴────┐                  │
│ │Ingest-│    │        │  │AI Prov-│     │     │Exporters│                  │
│ │ers    │    │        │  │iders   │     │     │(plugin) │                  │
│ │(plugin│    │        │  │(plugin)│     │     └─────────┘                  │
│ └───────┘    │        │  └────────┘     │                                  │
│              │        │                 │                                   │
│         ┌────┴────┐┌──┴──────┐   ┌─────┴─────┐                            │
│         │Intermed.││Assembled│   │  Book     │                             │
│         │Repr     ││Book     │   │  Manifest │                             │
│         │(HTML)   ││Content  │   │           │                             │
│         └─────────┘└─────────┘   └───────────┘                             │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐     │
│  │                     CROSS-CUTTING CONCERNS                          │     │
│  │  Config Loader │ Template Engine │ Metadata Reader │ Logger │ Worker│     │
│  └─────────────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The Six Pipeline Stages

Every conversion job passes through exactly six stages, in order. Stages 1–2 run **per-file** (in parallel). Stage 3 **aggregates** all files into a single book. Stages 4–6 run **per-book**.

```
Per-file (parallel)              Per-book (sequential)
┌─────────────────────┐          ┌─────────────────────────────────┐
│ File A → S1 → S2 ──┐│          │                                 │
│ File B → S1 → S2 ──┤├──→ S3 ──┤──→ S4 ──→ S5 ──→ S6 ──→ output│
│ File C → S1 → S2 ──┘│          │                                 │
└─────────────────────┘          └─────────────────────────────────┘
  Ingest   Normalize   Assemble    AI      Structure   Export
```

Each stage has a single responsibility and a well-defined input/output contract.

### Stage 1: Ingest

**Input:** Raw file (any supported format) + file metadata
**Output:** `RawContent` — extracted text/markup + detected metadata + embedded assets

```
┌──────────────────────────────────────────────────────────┐
│                      INGEST STAGE                         │
│                                                            │
│   file.html  ──→ HtmlIngester ──────┐                     │
│   file.md    ──→ MarkdownIngester ──┐│  (GFM: tables,     │
│                  (Pandoc GFM mode)  ││   fenced code,      │
│   file.txt   ──→ TxtIngester ──────┐││   task lists)       │
│                  (heuristic chapter ││││                     │
│                   break detection)  │││                     │
│   file.docx  ──→ DocxIngester ─────┤├┤├──→ RawContent      │
│   file.pdf   ──→ PdfIngester ──────┤│││  (PyMuPDF for      │
│                  (auto-detect scan  ││││   digital; OCR     │
│                   vs digital)       │││    for scanned)     │
│   file.epub  ──→ EpubIngester ─────┤││                     │
│   scan.tiff  ──→ OcrIngester ──────┘│                      │
│   scan.png   ──→ OcrIngester ───────┘                      │
│   scan.jpeg  ──→ OcrIngester ────────                      │
│   scan.bmp   ──→ OcrIngester ────────                      │
│                                                            │
│   Format detected via:                                     │
│   1. File extension                                        │
│   2. MIME type sniffing                                    │
│   3. Magic bytes (for PDFs: scanned vs digital detection)  │
└──────────────────────────────────────────────────────────────┘
```

**Key rules:**
- The ingester for scanned PDFs delegates to the OCR engine internally. The pipeline doesn't need to know.
- **OcrIngester** handles TIFF, PNG, JPEG, and BMP — all four scanned image formats the client requires.
- **MarkdownIngester** uses Pandoc with `--from gfm` (GitHub-Flavored Markdown) to support tables, fenced code blocks, and task lists.
- **TxtIngester** applies heuristic chapter break detection before producing RawContent:
  1. Blank-line-delimited paragraphs
  2. Lines matching `Chapter N`, `CHAPTER N`, or roman numerals (`Chapter IV`)
  3. ALL-CAPS lines as potential headings
  4. Lines matching common separator patterns (`---`, `***`, `===`)
  5. If heuristics produce no structure, optionally delegate to AI for structure inference (configurable: `pipeline.txt_ai_structure: true`)

### Stage 2: Normalize

**Input:** `RawContent` from any ingester
**Output:** `NormalizedContent` — clean semantic HTML with extracted assets, protected blocks tagged

```
┌──────────────────────────────────────────────────────────┐
│                    NORMALIZE STAGE                         │
│                                                            │
│   RawContent                                               │
│       │                                                    │
│       ▼                                                    │
│   HTML Cleaner ──→ Structure Detector ──→ Equation Detector│
│                                               │            │
│                                               ▼            │
│                                     Table Standardizer     │
│                                               │            │
│                                               ▼            │
│                                      NormalizedContent      │
│                                      ├── body_html         │
│                                      ├── detected_title    │
│                                      ├── detected_headings │
│                                      ├── protected_blocks[]│
│                                      ├── assets[]          │
│                                      └── source_metadata   │
└──────────────────────────────────────────────────────────────┘
```

The normalizer:
- Strips non-semantic markup (scripts, nav, style tags)
- Detects document structure (headings, chapters, sections)
- **Detects and tags equations** — LaTeX (`$...$`, `$$...$$`, `\begin{equation}`), MathML (`<math>`), and image-based equations. Each is wrapped in `<span class="bf-protected" data-type="equation">` so downstream stages know to skip them
- **Detects and tags tables** — each `<table>` gets `class="bf-protected"` so the AI rewriter preserves them verbatim
- **Detects and tags figure captions** — `<figcaption>` elements are protected from rewriting
- Standardizes table markup (consistent `<thead>/<tbody>`, standard attributes)
- Extracts and catalogs embedded images/assets
- Produces the **Intermediate Representation** — the single format all downstream stages consume

**Protected blocks** are the key innovation: anything wrapped in `class="bf-protected"` passes through AI rewriting untouched. This is how we guarantee equations, tables, and figures survive rewriting.

### Stage 3: Assemble (NEW — the per-file → per-book boundary)

**Input:** `list[NormalizedContent]` (one per input file) + `BookMetadata` from Excel
**Output:** `AssembledBook` — all articles merged into ordered chapters with aggregated metadata

```
┌───────────────────────────────────────────────────────────┐
│                   ASSEMBLE STAGE                           │
│                                                            │
│   NormalizedContent (article_1.pdf) ──┐                    │
│   NormalizedContent (article_2.html) ─┤                    │
│   NormalizedContent (article_3.docx) ─┘                    │
│          │                                                 │
│          ▼                                                 │
│   ┌─ Article Ordering                                      │
│   │  (Excel chapter_order column → row order → filename)   │
│   │                                                        │
│   ├─ Article Title Extraction                              │
│   │  (detected_title from each NormalizedContent)          │
│   │                                                        │
│   ├─ Content Concatenation                                 │
│   │  (each article becomes one chapter in body_html)       │
│   │                                                        │
│   ├─ Asset Deduplication                                   │
│   │  (merge assets from all articles, resolve conflicts)   │
│   │                                                        │
│   └─ Protected Block Renumbering                           │
│      (reindex PROTECTED_0..N across all articles)          │
│          │                                                 │
│          ▼                                                 │
│   AssembledBook                                            │
│   ├── body_html          (all articles as chapters)        │
│   ├── article_titles[]   (for AI title generation)         │
│   ├── chapter_headings[] (aggregated from all articles)    │
│   ├── protected_blocks[] (renumbered across all articles)  │
│   ├── assets[]           (deduplicated)                    │
│   └── metadata           (from Excel)                      │
└───────────────────────────────────────────────────────────┘
```

**Why this stage exists:** The client is an academic publisher. Their workflow is: 50 separate article files → one edited book volume. The AI title generator needs all article titles to produce a coherent book title. Without this aggregation step, each file would be processed independently and there'd be no way to generate a title from the collection.

**Article ordering logic:**
1. If Excel has a `chapter_order` column → use it (explicit)
2. Else → Excel row order (implicit, most common)
3. Else (single-file upload without Excel) → filename alphabetical sort

**Chapter wrapping:** Each article's `body_html` is wrapped in `<section class="bf-chapter" data-source="original_filename">`, with the article's `detected_title` promoted to `<h1>` if not already present.

---

### Stage 4: AI Processing

**Input:** `AssembledBook` + job configuration (rewrite %, generation flags)
**Output:** `ProcessedContent` — content with AI-generated/rewritten sections

```
┌──────────────────────────────────────────────────────┐
│                 AI PROCESSING STAGE                    │
│                                                       │
│   AssembledBook ──────┬──→ TitleGenerator              │
│                       │    (reads article_titles[] to  │
│                       │     generate book title)       │
│                       ├──→ PrefaceGenerator            │
│                       │    (reads full body for summary│
│                       ├──→ AcknowledgementGenerator    │
│                       └──→ ContentRewriter             │
│                                   │                   │
│                                   ▼                   │
│                            ProcessedContent           │
│                            ├── generated_title        │
│                            ├── generated_preface      │
│                            ├── generated_ack          │
│                            ├── rewritten_body_html    │
│                            └── ai_metadata            │
│                                                       │
│   Rewriter processes chapter-by-chapter:              │
│   - Splits HTML at <h1>/<h2> boundaries               │
│   - Extracts all bf-protected blocks, replaces with  │
│     placeholders: <<<PROTECTED_1>>>, <<<PROTECTED_2>>>│
│   - Sends cleaned chunk to AI (no equations/tables)   │
│   - Reinserts protected blocks at placeholder sites   │
│   - Reassembles preserving original structure         │
│                                                       │
│   Protected block flow:                               │
│   1. Extract: <span class="bf-protected">E=mc²</span>│
│      → replaced with <<<PROTECTED_0>>>                │
│   2. AI rewrites surrounding text only                │
│   3. <<<PROTECTED_0>>> → original block restored      │
│   This guarantees equations/tables/figures survive.    │
│                                                       │
│   Each sub-feature is independently toggleable:       │
│   - config.generate_title: true/false                 │
│   - config.generate_preface: true/false               │
│   - config.generate_acknowledgement: true/false       │
│   - config.rewrite_percent: 0 = skip rewriting        │
│   If ALL are off, entire stage is skipped.            │
│   If only some are on, only those generators run.     │
└──────────────────────────────────────────────────────┘
```

#### AI Rewriter: Token Budget & Sub-Chapter Splitting

The rewriter must handle chapters that exceed the AI model's context window. A single academic chapter can be 30,000+ tokens — larger than some models accept for a single rewrite call.

**Strategy: hierarchical splitting with token counting**

```python
def rewrite_chapter(chapter_html: str, rewrite_percent: int, 
                    ai_provider: BaseAIProvider, config: dict) -> str:
    """Rewrite a chapter, handling arbitrarily long content.
    
    1. Count tokens (using tiktoken or provider's tokenizer)
    2. If within budget (default: 80% of model max_tokens), rewrite as single call
    3. If over budget, split at paragraph boundaries (<p> tags)
       - Group paragraphs into chunks of ~3000 tokens each
       - Rewrite each chunk independently
       - Pass previous chunk's last paragraph as context to next chunk
         (overlapping context preserves coherence)
    4. Protected blocks are extracted BEFORE token counting
       (they don't count toward the budget since they're not sent to AI)
    """
    
    MAX_CHUNK_TOKENS = config.get("ai.max_chunk_tokens", 3000)
    
    # Extract protected blocks first
    text, placeholders = extract_protected_blocks(chapter_html)
    token_count = count_tokens(text, config.ai.model)
    
    if token_count <= MAX_CHUNK_TOKENS:
        rewritten = ai_provider.rewrite(text, build_instruction(rewrite_percent))
    else:
        chunks = split_at_paragraphs(text, MAX_CHUNK_TOKENS)
        rewritten_chunks = []
        prev_context = ""
        for chunk in chunks:
            rewritten = ai_provider.rewrite(
                chunk, 
                build_instruction(rewrite_percent),
                # CRITICAL: prev_context is passed as SYSTEM context (read-only),
                # NOT as text to rewrite. The prompt template says:
                # "The following is context from the previous section. Do NOT 
                #  rewrite it. Only rewrite the text after '---BEGIN REWRITE---'."
                # This prevents duplicate content from overlapping rewrites.
                system_context=prev_context
            )
            rewritten_chunks.append(rewritten)
            prev_context = chunk[-500:]  # NOTE: original text, not rewritten,
                                         # used as context for next chunk
        rewritten = join_chunks(rewritten_chunks)
    
    # Restore protected blocks
    return restore_protected_blocks(rewritten, placeholders)
```

**Token budget config:**
```yaml
ai:
  max_chunk_tokens: 3000         # Max tokens per rewrite call
  context_overlap_tokens: 200    # Trailing context for coherence between chunks
  model_max_tokens: 4096         # Model output limit
```

This guarantees the rewriter works on any chapter length — from 500-word abstracts to 50,000-word monographs.

### Stage 5: Structure

**Input:** `ProcessedContent` + book metadata (from Excel or config)
**Output:** `BookManifest` — ordered list of book sections, each with content and role

```
┌──────────────────────────────────────────────────────────┐
│                   STRUCTURE STAGE                          │
│                                                            │
│   ProcessedContent + BookMetadata + JobConfig              │
│          │                                                 │
│          ▼                                                 │
│   Conditional section assembly:                            │
│   ┌─ CoverPage         ← always (image or generated)      │
│   ├─ TitlePage          ← always (title + author)          │
│   ├─ CopyrightPage      ← always (template + variables)   │
│   ├─ Preface            ← ONLY IF generated or provided   │
│   ├─ Acknowledgement    ← ONLY IF generated or provided   │
│   ├─ TableOfContents    ← always (auto from headings)      │
│   ├─ Chapter 1..N       ← always (content)                 │
│   └─ Index              ← ONLY IF config.generate_index    │
│          │                                                 │
│          ▼                                                 │
│   BookManifest                                             │
│   ├── sections: List[BookSection]  (only included sections)│
│   ├── metadata: BookMetadata                               │
│   └── assets: List[Asset]                                  │
└──────────────────────────────────────────────────────────┘
```

**Conditional logic in `structure/builder.py`:**

```python
def build_manifest(content: ProcessedContent, metadata: BookMetadata,
                   config: JobConfig) -> BookManifest:
    """Assemble BookManifest with only the sections that apply.
    
    Sections are included/excluded based on:
    - Preface: included if content.generated_preface is not None
    - Acknowledgement: included if content.generated_acknowledgement is not None  
    - Index: included if config.generate_index is True (print only)
    - Cover/Title/Copyright/TOC/Chapters: always included
    """
    sections = []
    order = 0
    
    # Always included
    sections.append(BookSection(role=COVER, ...))
    sections.append(BookSection(role=TITLE_PAGE, ...))
    sections.append(BookSection(role=COPYRIGHT, ...))
    
    # Conditionally included
    if content.generated_preface:
        sections.append(BookSection(role=PREFACE, 
                                     content_html=content.generated_preface, ...))
    
    if content.generated_acknowledgement:
        sections.append(BookSection(role=ACKNOWLEDGEMENT,
                                     content_html=content.generated_acknowledgement, ...))
    
    # Always included
    sections.append(BookSection(role=TABLE_OF_CONTENTS, ...))
    for chapter in split_chapters(content.body_html):
        sections.append(BookSection(role=CHAPTER, ...))
    
    # Conditionally included (print only)
    if config.generate_index:
        sections.append(BookSection(role=INDEX, ...))
    
    return BookManifest(sections=sections, metadata=metadata, assets=content.assets)
```

If `generate_preface: false` was set in the job config, Stage 3 skips preface generation, `content.generated_preface` is `None`, and Stage 4 omits it from the manifest. Clean end-to-end.
```

### Stage 6: Export

**Input:** `BookManifest` + template + output format(s)
**Output:** Final files (EPUB, DOCX, PDF)

```
┌──────────────────────────────────────────────────────────┐
│                    EXPORT STAGE                            │
│                                                            │
│   BookManifest + Template                                  │
│        │                                                   │
│        ├──→ EpubExporter ──→ [Calibre polish] ──→ book.epub│
│        │    (ebooklib)        (optional)                   │
│        │                                                   │
│        ├──→ DocxExporter ──→ book.docx                     │
│        │    (python-docx + Pandoc)                         │
│        │    └── _apply_table_borders()  ← explicit borders │
│        │    └── _render_equations()     ← MathML/image     │
│        │                                                   │
│        └──→ PdfExporter  ──→ book.pdf                      │
│             (WeasyPrint)                                   │
│             └── _render_equations()     ← MathML/image     │
│                                                            │
│   Each exporter:                                           │
│   1. Loads template CSS/config for its format              │
│   2. Renders each BookSection with template styling        │
│   3. Applies format-specific post-processing:              │
│      - EPUB: Calibre polish (cover, metadata, cleanup)     │
│      - DOCX: python-docx table border manipulation         │
│      - PDF:  equation rendering via MathML or image fallback│
│   4. Assembles final document with metadata                │
│   5. Validates output (epubcheck, DOCX structure, etc.)    │
│                                                            │
│   Multiple formats can be produced in parallel             │
│   from the same BookManifest.                              │
└──────────────────────────────────────────────────────────────┘
```

#### EPUB: Calibre Integration

Calibre's `ebook-convert` is used as an **optional post-processing step**, not as the primary EPUB builder:

```
ebooklib builds EPUB structure (full control)
    → Calibre `ebook-polish` cleans up (optional)
    → Calibre `ebook-convert` can produce MOBI/AZW3 (future Kindle support)
```

Why both? ebooklib gives us programmatic control over every EPUB element. Calibre is better at edge cases: cover embedding, metadata normalization, and compatibility fixes across readers. Using both gives us control + polish.

If Calibre is not installed, the pipeline still works — ebooklib output is valid EPUB 3.0. Calibre is an enhancement, not a dependency.

#### DOCX: Table Border Post-Processing

CSS doesn't control DOCX table styling. The `DocxExporter` includes an explicit `_apply_table_borders()` step:

```python
def _apply_table_borders(self, doc: Document, template_config: dict):
    """Apply hairline grid borders to every table in the DOCX.
    
    Uses python-docx to set border properties directly on each 
    table cell, ensuring consistent rendering regardless of the
    reference document's default styles.
    
    Border config comes from template config.yaml:
      tables.border_style: "grid"
      tables.border_width: "0.25pt"
    """
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                set_cell_borders(cell, 
                    top={"sz": 2, "val": "single"},     # 0.25pt
                    bottom={"sz": 2, "val": "single"},
                    start={"sz": 2, "val": "single"},
                    end={"sz": 2, "val": "single"})
```

This guarantees hairline grid borders in Word regardless of template defaults.

#### DOCX: Headers, Footers, and Page Numbers

The DocxExporter also applies print-ready page formatting:

```python
def _apply_headers_footers(self, doc: Document, metadata: BookMetadata):
    """Add page numbers, book title header, and author footer.
    
    Uses python-docx section headers/footers:
    - Header: Book title (centered or right-aligned per template)
    - Footer: Page number (centered)
    - First page of each chapter: different header (chapter title)
    """
    for section in doc.sections:
        # Header: book title
        header = section.header
        header.paragraphs[0].text = metadata.title
        
        # Footer: page number
        footer = section.footer
        # Add PAGE field code for auto page numbers
        add_page_number(footer.paragraphs[0])
```

This is mandatory per client requirements: "Page numbers, headers/footers" for print-ready DOCX.

#### Equation Rendering Across Formats

Equations detected in Stage 2 are stored as their original source (LaTeX, MathML, or image). Each exporter handles them differently:

| Format | Primary Strategy | Fallback | Notes |
|---|---|---|---|
| EPUB | **Image (default)** | MathML (opt-in) | Kindle/KDP has poor MathML support. Image-first guarantees cross-reader compatibility. MathML opt-in via config for Apple Books/Kobo where it renders well. |
| DOCX | **Image** | OMML (experimental) | See risk note below. Image is the safe default. |
| PDF | MathML via WeasyPrint | LaTeX→image via matplotlib | WeasyPrint handles MathML well. Image fallback for edge cases. |

**EPUB equation decision:** The client requires Kindle/KDP compatibility (Req §4.1). Kindle's MathML support is unreliable. Therefore, **EPUB uses image-rendered equations by default**. This is configurable:

```yaml
# config/default.yaml
export:
  epub:
    equation_mode: "image"     # "image" (default, Kindle-safe) or "mathml" (Apple Books/Kobo)
```

**Image rendering pipeline:**
```
LaTeX source → matplotlib.mathtext → PNG (300 DPI) → embedded as <img> in EPUB/DOCX
MathML source → also rendered to PNG via matplotlib for image mode
```

All equation images are generated at export time, stored in the job's temp directory (file-backed Asset), and embedded in the final output.

#### ⚠ DOCX Equation Rendering — HIGH IMPLEMENTATION RISK

Converting LaTeX → OMML (Office Math Markup Language) is **the hardest equation rendering problem in this stack**. Here's why:

- `python-docx` has no built-in OMML support
- The conversion chain is: LaTeX → MathML → OMML (via Microsoft's XSLT stylesheet `MML2OMML.xsl`)
- The XSLT stylesheet is proprietary Microsoft, shipped with Office, not redistributable
- Alternative: use `latex2mathml` (Python) + custom MathML→OMML converter

**MVP Decision: DOCX uses image fallback for equations.**

This is pragmatic. Image-rendered equations in DOCX look correct in Word and print cleanly. OMML is a Phase 2 enhancement for clients who need editable equations in Word.

```python
# equation_renderer.py — DOCX path
def render_for_docx(equation: ProtectedBlock) -> Asset:
    """Render equation as image for DOCX embedding.
    
    MVP: Always image. Phase 2: OMML for editable equations.
    """
    png_path = render_equation_to_image(equation.original_html, dpi=300)
    return Asset(filename=f"eq_{equation.block_id}.png", 
                 media_type="image/png",
                 file_path=png_path,
                 size_bytes=png_path.stat().st_size)
```

Phase 2 OMML path (documented for future):
```
LaTeX → latex2mathml → MathML → lxml XSLT (MML2OMML.xsl) → OMML XML → python-docx OxmlElement
```

---

## 4. Data Models

These are the core data structures that flow between stages.

```python
# === Stage boundaries ===

@dataclass
class RawContent:
    """Output of Stage 1 (Ingest)."""
    text: str                        # Raw extracted text or markup
    format_hint: str                 # "html", "markdown", "plain", etc.
    assets: list[Asset]              # Embedded images, figures
    source_metadata: dict            # Anything detected from the file itself
    source_path: Path

@dataclass
class NormalizedContent:
    """Output of Stage 2 (Normalize)."""
    body_html: str                   # Clean semantic HTML (with bf-protected tags)
    detected_title: str | None
    detected_headings: list[Heading]
    protected_blocks: list[ProtectedBlock]  # Equations, tables, figures
    assets: list[Asset]
    source_metadata: dict

@dataclass
class AssembledBook:
    """Output of Stage 3 (Assemble). Aggregates multiple articles into one book."""
    body_html: str                   # All articles as chapters, ordered
    article_titles: list[str]        # Titles from all articles (for AI title generation)
    chapter_headings: list[Heading]  # Aggregated headings from all articles
    protected_blocks: list[ProtectedBlock]  # Renumbered across all articles
    assets: list[Asset]              # Deduplicated from all articles
    metadata: BookMetadata           # From Excel
    source_files: list[Path]         # Original file paths, in chapter order

@dataclass
class ProcessedContent:
    """Output of Stage 4 (AI Processing)."""
    body_html: str                   # Potentially rewritten HTML
    generated_title: str | None
    generated_preface: str | None
    generated_acknowledgement: str | None
    ai_metadata: dict                # Provider, model, tokens used, etc.

@dataclass
class BookSection:
    """One section of the final book."""
    role: SectionRole                # COVER, TITLE_PAGE, COPYRIGHT, PREFACE, etc.
    title: str
    content_html: str
    order: int

@dataclass
class BookManifest:
    """Output of Stage 4 (Structure). Input to Stage 5 (Export)."""
    sections: list[BookSection]
    metadata: BookMetadata
    assets: list[Asset]

@dataclass
class BookMetadata:
    """Metadata for the book — from Excel, config, or detection."""
    title: str
    authors: list[str]
    isbn: str | None
    eisbn: str | None
    publisher_name: str
    publisher_address: str | None
    publisher_email: str | None
    year: int
    language: str
    cover_image: Path | None

# === Supporting types ===

class SectionRole(Enum):
    COVER = "cover"
    TITLE_PAGE = "title_page"
    COPYRIGHT = "copyright"
    PREFACE = "preface"
    ACKNOWLEDGEMENT = "acknowledgement"
    TABLE_OF_CONTENTS = "toc"
    CHAPTER = "chapter"
    INDEX = "index"

@dataclass
class Asset:
    """An embedded file (image, font, etc.).
    
    Assets are file-backed, NOT memory-backed. The data lives on disk 
    in the job's temp directory. This prevents OOM on large PDFs with 
    many high-resolution images.
    """
    filename: str
    media_type: str
    file_path: Path              # Reference to temp file on disk (NOT bytes in memory)
    size_bytes: int
    
@dataclass
class Heading:
    """A detected heading in the content."""
    level: int                       # 1-6
    text: str
    anchor_id: str

class ProtectedBlockType(Enum):
    EQUATION = "equation"            # LaTeX, MathML, image-based math
    TABLE = "table"                  # Data tables
    FIGURE_CAPTION = "figure_caption"

@dataclass
class ProtectedBlock:
    """Content that must survive AI rewriting untouched."""
    block_id: str                    # "PROTECTED_0", "PROTECTED_1", etc.
    block_type: ProtectedBlockType
    original_html: str               # Exact original markup
    source_format: str               # "latex", "mathml", "html_table", "image"
```

---

## 5. Plugin Interfaces

Every replaceable component implements a base interface. The registry loads implementations by name from config.

### 5.1 Ingester Interface

```python
class BaseIngester(ABC):
    """Extracts content from a specific file format."""
    
    supported_extensions: list[str]   # e.g., [".html", ".htm"]
    supported_mimetypes: list[str]    # e.g., ["text/html"]
    
    @abstractmethod
    def can_handle(self, file_path: Path) -> bool:
        """Return True if this ingester can process the file."""
        
    @abstractmethod
    def ingest(self, file_path: Path, config: dict) -> RawContent:
        """Extract content from the file."""
```

### 5.2 OCR Engine Interface

```python
class BaseOCREngine(ABC):
    """Converts images/scanned documents to text."""
    
    @abstractmethod
    def ocr_image(self, image_path: Path, language: str) -> str:
        """OCR a single image, return extracted text."""
        
    @abstractmethod
    def ocr_pdf(self, pdf_path: Path, language: str) -> list[PageResult]:
        """OCR a scanned PDF, return per-page results."""
```

### 5.3 AI Provider Interface

```python
class BaseAIProvider(ABC):
    """Generates or rewrites text content."""
    
    @abstractmethod
    def generate(self, prompt: str, context: str, max_tokens: int) -> str:
        """Generate text given a prompt and context."""
        
    @abstractmethod
    def rewrite(self, text: str, instruction: str, max_tokens: int) -> str:
        """Rewrite text according to instruction."""
```

### 5.4 Exporter Interface

```python
class BaseExporter(ABC):
    """Renders a BookManifest into a specific output format."""
    
    output_format: str               # "epub", "docx", "pdf"
    
    @abstractmethod
    def export(self, manifest: BookManifest, template: Template, 
               output_path: Path) -> ExportResult:
        """Render the book to the target format."""
        
    @abstractmethod
    def validate(self, output_path: Path) -> ValidationResult:
        """Validate the produced output file."""
```

---

## 6. Component Registry

Components register by name. The pipeline resolves them at runtime from config.

```python
# Config says:
#   ocr.engine: "tesseract"
#   ai.provider: "anthropic"

# Registry maps:
#   "tesseract" → TesseractOCREngine
#   "anthropic" → AnthropicAIProvider
#   "openai"    → OpenAIProvider

# Pipeline resolves:
#   ocr_engine = registry.get_ocr_engine(config.ocr.engine)
#   ai_provider = registry.get_ai_provider(config.ai.provider)
```

Registration happens at import time via decorators:

```python
@register_ingester("html")
class HtmlIngester(BaseIngester):
    ...

@register_exporter("epub")
class EpubExporter(BaseExporter):
    ...

@register_ocr_engine("tesseract")
class TesseractOCREngine(BaseOCREngine):
    ...

@register_ai_provider("anthropic")
class AnthropicAIProvider(BaseAIProvider):
    ...
```

---

## 7. Template System Architecture

```
┌──────────────────────────────────────────────────────┐
│                  TEMPLATE SYSTEM                      │
│                                                       │
│  templates/academic/                                  │
│  ├── config.yaml ──→ TemplateConfig (parsed)         │
│  ├── styles.css  ──→ applied to EPUB + PDF           │
│  ├── print.css   ──→ applied to PDF only             │
│  ├── docx_reference.docx ──→ Pandoc --reference-doc  │
│  ├── copyright.html.jinja ──→ copyright page template│
│  ├── title_page.html.jinja ──→ title page template   │
│  └── fonts/                                           │
│      ├── CrimsonText-Regular.ttf                     │
│      └── SourceSansPro-Bold.ttf                      │
│                                                       │
│  Template Loading:                                    │
│  1. TemplateLoader reads config.yaml                 │
│  2. Validates required files exist                    │
│  3. Validates Jinja templates reference only variables│
│     defined in BookMetadata — unknown variables raise │
│     TemplateConfigError at load time, not render time │
│  4. Returns Template object with paths + parsed config│
│                                                       │
│  Template Application:                                │
│  - EPUB: embed styles.css + fonts into EPUB package  │
│  - DOCX: pass docx_reference.docx to Pandoc          │
│  - PDF:  apply styles.css + print.css via WeasyPrint  │
│                                                       │
│  Jinja templates for front-matter pages:              │
│  - Variables from BookMetadata fill in placeholders   │
│  - {{ isbn }}, {{ publisher_name }}, {{ year }}, etc.│
└──────────────────────────────────────────────────────┘
```

---

## 7b. Batch Orchestration: Excel → Multiple Jobs

The architecture has a clear driver for batch mode — the `metadata/reader.py` + `jobs/manager.py` collaborate:

```
┌────────────────────────────────────────────────────────────────┐
│                  BATCH ORCHESTRATION FLOW                       │
│                                                                 │
│  User uploads:                                                  │
│  ├── metadata.xlsx (one row per book)                           │
│  └── input_files/ (all manuscripts)                             │
│            │                                                    │
│            ▼                                                    │
│  ┌──────────────────┐                                           │
│  │ metadata/reader.py│   Reads Excel, applies column mapping    │
│  │                   │   from config/columns.yaml               │
│  └────────┬─────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐                                           │
│  │metadata/validator │   For each row:                          │
│  │                   │   1. Validate required fields present    │
│  │                   │   2. Strip author name credentials       │
│  │                   │   3. Resolve input_files glob patterns   │
│  │                   │   4. Apply defaults for missing optional │
│  └────────┬─────────┘                                           │
│           │                                                     │
│           ▼ List[BookMetadata + JobConfig]                       │
│  ┌──────────────────┐                                           │
│  │ jobs/manager.py   │   For each validated row:                │
│  │                   │   1. Create Job with BookMetadata        │
│  │                   │   2. Spawn worker subprocess             │
│  │                   │   3. Track batch-level progress          │
│  └────────┬─────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐                                           │
│  │ Batch Tracker     │   Aggregates across all jobs:            │
│  │                   │   { total_books: 12, completed: 8,       │
│  │                   │     failed: 1, in_progress: 3 }          │
│  └──────────────────┘                                           │
│                                                                 │
│  API endpoints:                                                 │
│  POST /api/v1/batches       → upload Excel + files → create all │
│  GET  /api/v1/batches/{id}  → batch-level progress              │
│  GET  /api/v1/jobs/{id}     → individual book progress          │
└────────────────────────────────────────────────────────────────┘
```

### Author Name Stripping

The `metadata/validator.py` enforces the client's rule: **only names, never designations/institutions/affiliations.**

```python
def strip_author_credentials(raw_name: str) -> str:
    """Strip academic/professional credentials from author name.
    
    Client requirement §5: "Only names allowed — NO designations, 
    institutions, affiliations."
    
    Examples:
      "Dr. John Smith, Ph.D., MIT" → "John Smith"
      "Prof. Jane Doe (University of Cambridge)" → "Jane Doe"
      "A. Kumar, M.D., FACP" → "A. Kumar"
    
    Strategy:
    1. Remove common prefixes: Dr., Prof., Mr., Mrs., Ms.
    2. Remove common suffixes: Ph.D., M.D., M.Sc., FACP, etc.
    3. Remove parenthetical content: (University of...)
    4. Remove text after comma that contains institution keywords
    5. Strip and normalize whitespace
    """
```

This runs during metadata validation, before any Job is created. Invalid or empty names after stripping are flagged as validation errors.

---

## 8. Batch Processing & Job Model

```
┌───────────────────────────────────────────────────────────┐
│                    JOB LIFECYCLE                            │
│                                                            │
│   CREATED ──→ QUEUED ──→ PROCESSING ──→ COMPLETED         │
│                              │              │              │
│                              ▼              ▼              │
│                          PARTIALLY      (with report)      │
│                           FAILED                           │
│                              │                             │
│                              ▼                             │
│                       (with error log)                     │
│                                                            │
│  A Job contains:                                           │
│  ├── job_id: UUID                                          │
│  ├── status: JobStatus                                     │
│  ├── input_files: list[Path]                               │
│  ├── metadata: BookMetadata                                │
│  ├── config: JobConfig (template, rewrite%, formats)       │
│  ├── progress: JobProgress          ← REAL-TIME TRACKING   │
│  │   ├── total_files: int                                  │
│  │   ├── completed_files: int                              │
│  │   ├── current_file: str | None                          │
│  │   ├── current_stage: str | None                         │
│  │   ├── succeeded: int                                    │
│  │   ├── failed: int                                       │
│  │   └── elapsed_seconds: float                            │
│  ├── file_results: list[FileResult]                        │
│  │   ├── file_path                                         │
│  │   ├── status: success | failed | skipped                │
│  │   ├── error: str | None                                 │
│  │   └── output_paths: list[Path]                          │
│  ├── created_at                                            │
│  ├── completed_at                                          │
│  └── report: BatchReport                                   │
│                                                            │
│  Batch Mode:                                               │
│  - Excel provides one row per book                         │
│  - Each row becomes one Job                                │
│  - Files within a job run in parallel (semaphore-bounded)  │
│  - One file failure never kills the batch                  │
└───────────────────────────────────────────────────────────┘
```

### MVP: Subprocess Worker with File-Based State

The MVP uses a **subprocess-based worker** with file-based state persistence. No Celery, no Redis, no infrastructure — but production-worthy: survives API restarts, tracks progress, resumes from checkpoint.

```
┌──────────────────────────────────────────────────────────┐
│                WORKER ARCHITECTURE (MVP)                   │
│                                                            │
│  API Process                    Worker Process             │
│  ┌──────────┐                  ┌─────────────┐            │
│  │ POST /job │──→ writes ──→   │ job.json    │            │
│  │           │   job config    │ (on disk)   │            │
│  │           │──→ spawns ──→   │             │            │
│  │           │   subprocess    └──────┬──────┘            │
│  │           │                       │                    │
│  │ GET /job  │                       ▼                    │
│  │  /{id}    │◀── reads ◀──   ┌─────────────┐            │
│  │           │   status file  │ Worker runs  │            │
│  └──────────┘                 │ pipeline     │            │
│                               │              │            │
│                               │ Writes per-  │            │
│                               │ file status  │            │
│                               │ to disk after│            │
│                               │ each file    │            │
│                               └──────────────┘            │
│                                                            │
│  data/jobs/{job_id}/                                       │
│  ├── job.json          # Job config (written by API)       │
│  ├── status.json       # Current progress (written by      │
│  │                     # worker, read by API for polling)   │
│  ├── results/          # Per-file results                  │
│  │   ├── file_001.json # { status, output_paths, error }   │
│  │   └── file_002.json                                     │
│  └── output/           # Generated books                   │
│      ├── book.epub                                         │
│      ├── book.docx                                         │
│      └── book.pdf                                          │
└──────────────────────────────────────────────────────────┘
```

**Why not BackgroundTasks?** BackgroundTasks runs in-process with the web server. For 100-file batches taking hours:
- Server restart kills the job with no recovery
- No progress persistence (if it dies at file 87, restart from 0)
- Memory pressure accumulates across 100 sequential files
- Web server event loop partially blocked

**Why not Celery for MVP?** Requires Redis infrastructure, adds deployment complexity. The subprocess worker gives 90% of the benefit with zero dependencies.

### File-Level Parallelism

Files within a batch are independent — process them concurrently:

```python
async def run_job(job: Job):
    semaphore = asyncio.Semaphore(job.config.max_concurrent_files)  # default: 4
    
    async def process_one(file_path: Path):
        async with semaphore:
            result = await pipeline.process_file(file_path, job.config)
            write_file_result(job.job_id, file_path, result)  # persist to disk
            update_progress(job.job_id)                        # update status.json
            return result
    
    results = await asyncio.gather(
        *[process_one(f) for f in job.input_files],
        return_exceptions=True  # one failure doesn't cancel others
    )
    return build_batch_report(results)
```

With `max_concurrent_files: 4`, a 100-file batch runs ~4x faster. OCR and AI calls are I/O-bound, so parallelism is effective even on a single core.

### Phase 2 Upgrade Path

When multi-user or horizontal scaling is needed:
1. Replace subprocess worker with Celery workers
2. Replace file-based store with PostgreSQL
3. Add `user_id` to Job model
4. Replace local file storage with S3-compatible object store
5. Redis for task broker + result backend

The Job model, pipeline stages, and API endpoints remain unchanged — only the worker and store layers swap.

### Progress Tracking: Polling vs Push

**MVP: Polling at 2-second interval.**

```
UI (JavaScript) ──→ GET /api/v1/jobs/{id} every 2 seconds
                     └── returns JobProgress JSON
                         { total_files: 100, completed: 47, 
                           current_file: "article_48.pdf",
                           current_stage: "ai_rewriting",
                           succeeded: 45, failed: 2 }
```

The API reads `data/jobs/{id}/status.json` from disk (written by the worker after each file completes). This is simple, reliable, and needs no WebSocket infrastructure.

**Phase 2: Server-Sent Events (SSE).**

For real-time push updates without polling overhead:
```
GET /api/v1/jobs/{id}/stream  → SSE endpoint
  data: {"completed": 47, "current_file": "article_48.pdf", ...}
  data: {"completed": 48, "current_file": "article_49.pdf", ...}
```

SSE is simpler than WebSocket (unidirectional, HTTP-native, auto-reconnect). FastAPI supports it via `StreamingResponse`. Not needed for MVP single-user, but documented for the frontend developer.

### API Endpoints (Complete)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/jobs` | Create a single conversion job |
| `GET` | `/api/v1/jobs` | List all jobs with status |
| `GET` | `/api/v1/jobs/{id}` | Get job details + progress |
| `GET` | `/api/v1/jobs/{id}/download` | Download completed output files |
| `DELETE` | `/api/v1/jobs/{id}` | Cancel a running job |
| `POST` | `/api/v1/batches` | Upload Excel + files → create multiple jobs |
| `GET` | `/api/v1/batches/{id}` | Batch-level progress across all books |
| `GET` | `/api/v1/templates` | List available templates |
| `GET` | `/api/v1/config` | Get current system configuration |
| `GET` | `/health` | Dependency health check |

---

## 9. Configuration Architecture

```
┌──────────────────────────────────────────────────────┐
│               CONFIGURATION LAYERS                    │
│                                                       │
│   Layer 1: config/default.yaml                        │
│   └── System defaults (always loaded)                 │
│                                                       │
│   Layer 2: config/local.yaml (git-ignored)            │
│   └── Local overrides (API keys, paths)               │
│                                                       │
│   Layer 3: Environment variables                      │
│   └── BOOKFORGE_AI_API_KEY, etc.                      │
│                                                       │
│   Layer 4: Job-level config                           │
│   └── Per-job overrides from API/Excel                │
│                                                       │
│   Merge order: default → local → env → job            │
│   Later layers override earlier ones.                 │
│                                                       │
│   Separate config files:                              │
│   ├── config/default.yaml     # Main system config    │
│   ├── config/columns.yaml     # Excel column mapping  │
│   └── config/prompts/         # AI prompt templates   │
│       ├── title.txt                                   │
│       ├── preface.txt                                 │
│       ├── acknowledgement.txt                         │
│       └── rewrite.txt                                 │
└──────────────────────────────────────────────────────┘
```

---

## 10. Error Handling Strategy

```
┌──────────────────────────────────────────────────────┐
│              ERROR BOUNDARIES                         │
│                                                       │
│  Level 1: File-level isolation                        │
│  ┌──────────────────────────────────┐                │
│  │  try:                            │                │
│  │    result = pipeline.process(f)  │                │
│  │  except IngestionError:          │  Per-file      │
│  │    log + skip + continue batch   │  try/except    │
│  │  except AIError:                 │                │
│  │    retry 3x → skip AI → continue│                │
│  │  except ExportError:             │                │
│  │    log + skip format → continue  │                │
│  └──────────────────────────────────┘                │
│                                                       │
│  Level 2: Stage-level errors                          │
│  - Each stage raises typed exceptions:                │
│    IngestionError, NormalizationError, AIError,       │
│    StructureError, ExportError                        │
│  - Pipeline catches at file boundary, never at batch  │
│                                                       │
│  Level 3: Batch report                                │
│  - After batch completes, generate BatchReport:       │
│    { succeeded: 47, failed: 2, skipped: 1,           │
│      errors: [{file, stage, message}, ...] }          │
│                                                       │
│  Critical principle:                                  │
│  ONE FILE FAILING NEVER KILLS THE BATCH.              │
└──────────────────────────────────────────────────────┘
```

---

## 11. Folder Structure

```
bookforge/
│
├── pyproject.toml                    # Project metadata, dependencies, build config
├── Dockerfile                        # Container build
├── docker-compose.yml                # Full stack (app + redis for Phase 2)
├── Makefile                          # Common commands: make run, make test, make build
├── .env.example                      # Template for local env vars
├── .gitignore
│
├── data/                             # Runtime data (git-ignored)
│   └── jobs/                         # Per-job directories with state + output
│       └── {job_id}/
│           ├── job.json              # Job config
│           ├── status.json           # Progress (worker writes, API reads)
│           ├── results/              # Per-file result JSONs
│           ├── temp/                 # Intermediate files (cleaned up after)
│           └── output/               # Final generated books
│
├── config/                           # ALL external configuration lives here
│   ├── default.yaml                  # System defaults
│   ├── columns.yaml                  # Excel column name mapping
│   └── prompts/                      # AI prompt templates (editable without code)
│       ├── title.txt
│       ├── preface.txt
│       ├── acknowledgement.txt
│       └── rewrite.txt
│
├── templates/                        # Styling templates (content-free)
│   ├── academic/
│   │   ├── config.yaml               # Typography, geometry, table rules
│   │   ├── styles.css                # EPUB + base styling
│   │   ├── print.css                 # PDF-specific overrides
│   │   ├── docx_reference.docx       # Pandoc reference doc for DOCX styling
│   │   ├── copyright.html.jinja      # Copyright page template
│   │   ├── title_page.html.jinja     # Title page template
│   │   └── fonts/
│   │       ├── CrimsonText-Regular.ttf
│   │       └── SourceSansPro-Bold.ttf
│   │
│   └── modern/
│       ├── config.yaml
│       ├── styles.css
│       ├── print.css
│       ├── docx_reference.docx
│       ├── copyright.html.jinja
│       ├── title_page.html.jinja
│       └── fonts/
│
├── bookforge/                        # Source code — the Python package
│   ├── __init__.py                   # Package version
│   │
│   ├── main.py                       # FastAPI application entry point
│   │
│   ├── core/                         # Pipeline engine + shared infrastructure
│   │   ├── __init__.py
│   │   ├── pipeline.py               # The 6-stage orchestrator
│   │   ├── models.py                 # All data models (RawContent → BookManifest)
│   │   ├── config.py                 # Config loader (YAML + env + merge)
│   │   ├── registry.py               # Component registry (decorators + lookup)
│   │   ├── exceptions.py             # Typed exceptions per stage
│   │   └── logging.py               # Structured logging setup
│   │
│   ├── ingestion/                    # Stage 1: Format-specific content extraction
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseIngester interface
│   │   ├── detector.py               # File format detection (extension + MIME + magic)
│   │   ├── html_ingester.py          # HTML → RawContent
│   │   ├── markdown_ingester.py      # Markdown → RawContent
│   │   ├── txt_ingester.py           # Plain text → RawContent
│   │   ├── docx_ingester.py          # DOCX → RawContent
│   │   ├── pdf_ingester.py           # PDF → RawContent (digital + scanned routing)
│   │   ├── epub_ingester.py          # EPUB → RawContent (for reverse conversion)
│   │   └── ocr/
│   │       ├── __init__.py
│   │       ├── base.py               # BaseOCREngine interface
│   │       └── tesseract.py          # Tesseract implementation
│   │
│   ├── assembly/                     # Stage 3: Aggregate articles into one book
│   │   ├── __init__.py
│   │   ├── assembler.py              # Merge multiple NormalizedContent → AssembledBook
│   │   ├── ordering.py               # Article ordering logic (Excel → row order → filename)
│   │   └── deduplicator.py           # Asset deduplication, protected block renumbering
│   │
│   ├── normalization/                # Stage 2: Convert to clean semantic HTML
│   │   ├── __init__.py
│   │   ├── normalizer.py             # Main normalizer — dispatches by format_hint
│   │   ├── html_cleaner.py           # Strip non-semantic elements, fix structure
│   │   ├── structure_detector.py     # Detect headings, chapters, sections
│   │   ├── equation_detector.py      # Detect LaTeX/MathML/image equations, tag as protected
│   │   └── table_standardizer.py     # Normalize + tag tables as protected
│   │
│   ├── ai/                           # Stage 4: AI generation and rewriting
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseAIProvider interface
│   │   ├── anthropic_provider.py     # Claude implementation
│   │   ├── openai_provider.py        # OpenAI implementation
│   │   ├── generator.py              # Title, preface, acknowledgement generation
│   │   ├── rewriter.py               # Content rewriting (chunked, structure-preserving)
│   │   └── prompt_loader.py          # Load prompts from config/prompts/
│   │
│   ├── structure/                    # Stage 5: Assemble book sections
│   │   ├── __init__.py
│   │   ├── builder.py                # BookManifest assembler
│   │   ├── front_matter.py           # Title page, copyright, preface, ack generators
│   │   └── toc_generator.py          # Table of contents from headings
│   │
│   ├── export/                       # Stage 6: Render to output formats
│   │   ├── __init__.py
│   │   ├── base.py                   # BaseExporter interface
│   │   ├── epub_exporter.py          # BookManifest → EPUB via ebooklib
│   │   ├── docx_exporter.py          # BookManifest → DOCX via python-docx + Pandoc
│   │   ├── pdf_exporter.py           # BookManifest → PDF via WeasyPrint
│   │   ├── calibre_polish.py         # Optional Calibre post-processing for EPUB
│   │   ├── docx_table_borders.py     # python-docx hairline grid border application
│   │   └── equation_renderer.py      # Equation rendering: MathML/OMML/image per format
│   │
│   ├── metadata/                     # Excel metadata reading + validation
│   │   ├── __init__.py
│   │   ├── reader.py                 # Read Excel, apply column mapping
│   │   └── validator.py              # Validate required fields, strip author creds
│   │
│   ├── templates/                    # Template loading and application
│   │   ├── __init__.py
│   │   ├── loader.py                 # Load template dir → Template object
│   │   └── engine.py                 # Apply template to BookManifest for export
│   │
│   ├── jobs/                         # Job management + worker
│   │   ├── __init__.py
│   │   ├── manager.py                # Create, track, query jobs
│   │   ├── models.py                 # Job, FileResult, BatchReport, JobProgress
│   │   ├── store.py                  # File-based store (MVP); DB adapter (Phase 2)
│   │   └── worker.py                 # Subprocess worker: reads job.json, runs pipeline, writes status
│   │
│   ├── api/                          # REST API routes
│   │   ├── __init__.py
│   │   ├── routes.py                 # All API endpoints
│   │   └── schemas.py                # Request/response Pydantic schemas
│   │
│   └── cli.py                        # CLI entry point (Click or Typer)
│
├── tests/                            # All tests
│   ├── conftest.py                   # Shared fixtures, sample file paths
│   ├── fixtures/                     # Test input files
│   │   ├── sample.html
│   │   ├── sample.md
│   │   ├── sample.txt
│   │   ├── sample.docx
│   │   ├── sample.pdf
│   │   ├── sample.epub
│   │   ├── sample_scan.tiff
│   │   └── sample_metadata.xlsx
│   │
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_registry.py
│   │   ├── test_ingestion_html.py
│   │   ├── test_ingestion_markdown.py
│   │   ├── test_ingestion_txt.py
│   │   ├── test_ingestion_docx.py
│   │   ├── test_ingestion_pdf.py
│   │   ├── test_normalizer.py
│   │   ├── test_structure_detector.py
│   │   ├── test_table_standardizer.py
│   │   ├── test_ai_generator.py
│   │   ├── test_ai_rewriter.py
│   │   ├── test_structure_builder.py
│   │   ├── test_toc_generator.py
│   │   ├── test_metadata_reader.py
│   │   ├── test_template_loader.py
│   │   ├── test_export_epub.py
│   │   ├── test_export_docx.py
│   │   └── test_export_pdf.py
│   │
│   └── integration/
│       ├── test_pipeline_html_to_epub.py
│       ├── test_pipeline_md_to_epub.py
│       ├── test_pipeline_txt_to_epub.py
│       ├── test_pipeline_docx_to_epub.py
│       ├── test_pipeline_pdf_to_epub.py
│       ├── test_pipeline_multi_format_output.py
│       ├── test_batch_processing.py
│       └── test_api_endpoints.py
│
├── samples/                          # Demo files for client showcase
│   ├── input/
│   │   ├── article1.html
│   │   ├── article2.md
│   │   ├── article3.txt
│   │   └── metadata.xlsx
│   └── output/                       # Generated sample outputs (git-tracked)
│       ├── book_academic.epub
│       ├── book_academic.docx
│       ├── book_academic.pdf
│       ├── book_modern.epub
│       └── batch_report.json
│
└── docs/
    ├── REQUIREMENTS.md               # Full requirements specification
    ├── ARCHITECTURE.md               # This file
    ├── SETUP.md                      # Installation + quickstart
    ├── CONFIGURATION.md              # All config options explained
    ├── TEMPLATES.md                  # How to create/modify templates
    └── API.md                        # REST API reference
```

---

## 12. Dependency Graph

```
                    ┌──────────┐
                    │  config  │
                    └────┬─────┘
                         │ (loaded first, used by everything)
            ┌────────────┼────────────────┐
            ▼            ▼                ▼
      ┌──────────┐ ┌──────────┐    ┌───────────┐
      │ registry │ │ templates│    │  metadata  │
      └────┬─────┘ └────┬─────┘    └─────┬─────┘
           │             │                │
           ▼             │                │
     ┌───────────┐       │                │
     │ ingestion │       │                │  Per-file
     └─────┬─────┘       │                │  (parallel)
           ▼             │                │
   ┌──────────────┐      │                │
   │normalization │      │                │
   └──────┬───────┘      │                │
          ▼              │                │
    ┌──────────┐         │                │
    │ assembly │◀────────│────────────────┘  ← per-file → per-book boundary
    └────┬─────┘         │                   (metadata feeds into assembly)
          ▼              │                │
     ┌─────────┐         │                │
     │   ai    │         │                │  Per-book
     └────┬────┘         │                │  (sequential)
          ▼              │                │
    ┌───────────┐        │                │
    │ structure │◀───────┘                │
    └─────┬─────┘    (template feeds into structure)
          ▼
     ┌──────────┐
     │  export  │◀── templates (styling applied at export)
     └────┬─────┘
          ▼
     ┌──────────┐
     │   jobs   │ (wraps pipeline, tracks status)
     └────┬─────┘
          ▼
    ┌───────────┐
    │  api/cli  │ (entry points)
    └───────────┘
```

**Import rule:** arrows point downward only. No module imports from a module below it. `core/` is shared infrastructure — everyone can import from `core/`. The `assembly/` module sits at the per-file → per-book boundary.

---

## 13. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Intermediate format | Semantic HTML | Universal — all inputs can produce it, all outputs can consume it. Pandoc already uses HTML internally. |
| Protected blocks | `bf-protected` class tags | Equations, tables, figures tagged in normalization → rewriter extracts as placeholders → restored after AI. Guarantees zero mutation of protected content. |
| MVP queue | Subprocess worker + file-based state | Survives API restarts. No Redis/Celery. Progress persisted to disk. Clear Celery upgrade path for Phase 2. |
| Template engine | Jinja2 for front-matter pages | Industry standard, already a FastAPI/Flask dependency, simple variable replacement. |
| EPUB library | ebooklib + Calibre polish | ebooklib for programmatic control. Calibre optional post-processing for metadata/cover/compatibility fixes. |
| DOCX table borders | python-docx direct manipulation | CSS doesn't control DOCX tables. Explicit `set_cell_borders()` on every cell guarantees hairline grid borders. |
| PDF engine | WeasyPrint (MVP) | Free, CSS-based, high-quality digital PDF. NOT press-quality (no bleed/CMYK/PDF-A). PrinceXML as Phase 2 opt-in via `pdf.engine: "prince"`. |
| Equation rendering | Format-specific: MathML (EPUB), OMML (DOCX), image fallback | No single equation format works everywhere. Each exporter handles its native format. Image fallback (300 DPI via matplotlib) is the universal safety net. |
| Config format | YAML | Human-readable, supports nesting, standard in Python ecosystem. |
| OCR | Tesseract via pytesseract | Free, mature. Interface allows swap to Google Vision, AWS Textract later. |
| Plugin pattern | Decorator-based registry | Minimal boilerplate. Add a new ingester = one file + one decorator. No config wiring needed. |
| AI chunking | Split at heading boundaries | Preserves document structure. Avoids truncation mid-paragraph. Respects token limits. |

---

## 14. External Tool Dependencies

These must be installed on the host (or in Docker):

| Tool | Required | Purpose | Install |
|---|---|---|---|
| Pandoc | **Yes** | DOCX conversion, Markdown (GFM) processing | `apt install pandoc` / `brew install pandoc` |
| Tesseract | **Yes** | OCR for scanned files (TIFF, PNG, JPEG, BMP) | `apt install tesseract-ocr` / `brew install tesseract` |
| WeasyPrint system deps | **Yes** | PDF generation | `apt install libpango...` (see WeasyPrint docs) |
| Calibre | **Optional** | EPUB polishing, MOBI/AZW3 conversion | `apt install calibre` / `brew install calibre` |

**Python library dependencies** (installed via pip/pyproject.toml):

| Library | Purpose |
|---|---|
| PyMuPDF (fitz) | PDF text/image extraction in `pdf_ingester.py` — primary PDF processing library |
| pytesseract | Python bindings for Tesseract OCR |
| pypandoc | Python bindings for Pandoc |
| ebooklib | EPUB 3.0 creation |
| python-docx | DOCX creation and table border manipulation |
| weasyprint | CSS-based PDF generation |
| openpyxl | Excel (.xlsx) reading |
| anthropic / openai | AI provider SDKs |
| Jinja2 | Template rendering for front-matter pages |
| Pillow | Image processing (OCR preprocessing, equation image rendering) |
| matplotlib | LaTeX equation → image fallback rendering |
| pydantic | Data validation, API schemas, job models |
| typer | CLI entry point |
| pyyaml | Configuration loading |

Calibre is optional — the pipeline produces valid EPUB without it. When installed, it's used for:
- `ebook-polish`: metadata cleanup, cover optimization, EPUB compatibility fixes
- `ebook-convert`: future MOBI/AZW3/KDP output (Phase 2)

The system auto-detects Calibre at startup. If not found, the polish step is skipped silently.

The Dockerfile will bundle all required tools. Calibre is included in the Docker image by default.

### Health Check

The `/health` endpoint performs real dependency checks:

```json
{
  "status": "healthy",
  "checks": {
    "worker": "idle",
    "tesseract": "installed (v5.3.1)",
    "pandoc": "installed (v3.1)",
    "calibre": "installed (v7.2)",
    "pymupdf": "installed (v1.24)",
    "ai_provider": "reachable (anthropic)",
    "disk_free_gb": 24.5,
    "active_jobs": 0
  }
}
```

This enables build server monitoring and fast diagnosis when things break.

---

## 15. What's NOT in MVP

Explicitly deferred to Phase 2:

- Celery + Redis (use subprocess worker with file-based state instead)
- Authentication / multi-user
- Database persistence for jobs (use file-based JSON store instead)
- Cloud storage (S3/GCS)
- Multi-language OCR
- Advanced indexing / back-of-book index
- KindleGen / KDP-specific output (Calibre `ebook-convert` prep is in place)
- Webhook notifications
- ONIX metadata export
- AI cost estimation before job start ("This batch will use ~$15")
- Plagiarism similarity scoring
