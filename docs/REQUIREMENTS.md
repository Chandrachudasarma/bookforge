# BookForge — Requirements Document

**Version:** 2.0
**Date:** 2026-04-05
**Status:** Implemented — see IMPLEMENTATION.md for build status

---

## 1. Project Summary

BookForge is an automated publishing pipeline that converts multiple input document formats into publication-ready EPUB books, with optional DOCX and high-quality digital PDF output. The system uses AI for content generation (titles, prefaces, acknowledgements) and content rewriting, processes files in batch, and reads metadata from Excel spreadsheets.

The system is modular, config-driven, and designed for long-term expansion.

---

## 2. Goals

1. **Automate end-to-end book production** — from raw manuscript files to publication-ready output with minimal manual intervention.
2. **Handle diverse inputs** — scanned images (OCR), PDF, HTML, DOCX, EPUB, Markdown, plain text.
3. **AI-powered content** — generate book front-matter and rewrite content at configurable expansion/reduction levels.
4. **Template-driven styling** — swap or extend layout templates without touching pipeline code.
5. **Batch processing** — handle 50–100 files per batch reliably.
6. **Config over code** — no hardcoded Excel columns, templates, or AI prompts.

---

## 3. Input Formats

### 3.1 Scanned Files (Images)

| Attribute | Detail |
|---|---|
| Formats | TIFF, PNG, JPEG, BMP |
| Processing | OCR via Tesseract (replaceable engine) |
| Requirements | Output must be structured and editable; preserve formatting as much as possible |
| Challenges | Tables in scans, multi-column layouts, mixed text/image pages |

### 3.2 PDF Files

| Attribute | Detail |
|---|---|
| Detection | Auto-detect scanned (image-based) vs digital (text-based) PDF |
| Scanned PDF | Route through OCR pipeline |
| Digital PDF | Extract text directly, preserve headings, tables, layout |
| Library | PyMuPDF (fitz) for text extraction; fallback to OCR for image-heavy pages |

### 3.3 HTML Files

| Attribute | Detail |
|---|---|
| Processing | Direct conversion, preserve formatting |
| Handling | Strip non-content elements (nav, scripts, ads); keep semantic structure |

### 3.4 Markdown Files

| Attribute | Detail |
|---|---|
| Processing | Convert to intermediate HTML, then to target format |
| Extensions | Support GitHub-Flavored Markdown (tables, fenced code, task lists) |

### 3.5 Plain Text (TXT)

| Attribute | Detail |
|---|---|
| Processing | Detect paragraph breaks, apply basic structure |
| Limitations | No inherent formatting — system infers chapter breaks via heuristics or AI |

### 3.6 Word (DOCX) Files

| Attribute | Detail |
|---|---|
| Processing | Convert to EPUB with formatting intact |
| Preserve | Styles, headings, tables, images, footnotes |
| Library | python-docx for reading; Pandoc for conversion |

### 3.7 EPUB Files (Reverse Conversion)

| Attribute | Detail |
|---|---|
| Processing | Convert EPUB → DOCX (print-ready) and/or PDF |
| Generate | Table of Contents, optional Index |

---

## 4. Output Formats

### 4.1 EPUB (Primary)

- Clean, valid EPUB 3.0 structure
- Compatible with major e-readers (Kindle via KindleGen/KDP, Apple Books, Kobo, Google Play)
- Embedded CSS from selected template
- Proper metadata (title, author, ISBN, publisher, language)
- Cover image support

### 4.2 DOCX (Print-Ready)

- Proper heading hierarchy
- Table of Contents (auto-generated)
- Page numbers, headers/footers
- Print-appropriate margins and fonts
- Tables with grid borders (hairline, ~0.25pt)

### 4.3 PDF (High-Quality Digital)

- High-resolution output (300 DPI minimum for images)
- Proper page geometry (trim size, margins)
- Embedded fonts
- Tables with grid borders (hairline, ~0.25pt)

**MVP limitation (WeasyPrint):** The default PDF engine produces high-quality digital PDF suitable for screen reading, digital distribution, and standard printing. It does NOT support:
- Bleed area / crop marks (required for offset printing)
- CMYK color model (outputs RGB only)
- PDF/A archival compliance (unreliable in WeasyPrint)
- Advanced OpenType features (ligatures, contextual alternates)

**Phase 2 upgrade:** For true press-ready PDF (offset printing, ISBN registration with PDF/A), the architecture includes a `pdf.engine` config option. Setting `pdf.engine: "prince"` (PrinceXML, commercial license ~$3,800/yr) enables bleed, crop marks, CMYK, and PDF/A. The exporter interface is the same — only the rendering engine swaps.

---

## 5. Book Structure

Every output book must include the following sections, in order:

| # | Section | Source |
|---|---|---|
| 1 | **Cover Page** | Provided image or auto-generated |
| 2 | **Title Page** | AI-generated title + editor/author name from Excel |
| 3 | **Copyright Page** | Template-based; variables: ISBN, eISBN, year, publisher name, address, email |
| 4 | **Preface** | AI-generated based on content analysis |
| 5 | **Acknowledgement** | AI-generated |
| 6 | **Table of Contents** | Auto-generated from chapter headings |
| 7 | **Chapters** | Converted articles/content |
| 8 | **Index** | Optional, auto-generated for print output |

---

## 6. AI Features

### 6.1 Content Generation

| Feature | Detail |
|---|---|
| Book Title | Generated from article titles and content themes |
| Preface | Generated from content summary; ~500–1000 words |
| Acknowledgement | Generated; professional and contextual |
| Provider | Configurable — Claude API (default), OpenAI, or other |
| Prompts | Stored in external config files, editable without code changes |

### 6.2 Content Rewriting

| Feature | Detail |
|---|---|
| Expansion/Reduction Levels | ±10%, ±25%, ±40%, ±60%, ±80%, ±100% |
| Constraints | Must preserve document structure (headings, sections) |
| Constraints | Must NOT modify equations, tables, or figure captions |
| Constraints | Must avoid plagiarism — paraphrase, don't copy |
| Constraints | Must maintain technical accuracy |
| Implementation | Process chapter-by-chapter; never rewrite in one monolithic call |

---

## 7. Metadata Input

### 7.1 Excel-Based Metadata

The system reads metadata from an Excel file (.xlsx) with the following rules:

- **Dynamic column mapping** — column names are configured externally, never hardcoded
- **Missing field handling** — graceful defaults when optional fields are absent
- **Required fields** — system validates presence of required fields before processing
- **One row per book** (or per article within a book, depending on mode)

### 7.2 Expected Metadata Fields

| Field | Required | Description |
|---|---|---|
| `title` | Optional | Override AI-generated title |
| `author_name` | Yes | Author/editor name (name only — no designations, institutions, affiliations) |
| `isbn` | Optional | ISBN for print edition |
| `eisbn` | Optional | eISBN for digital edition |
| `publisher_name` | Yes | Publisher name |
| `publisher_address` | Optional | Publisher address |
| `publisher_email` | Optional | Publisher contact email |
| `year` | Optional | Publication year (defaults to current year) |
| `language` | Optional | Content language (defaults to English) |
| `input_files` | Yes | Comma-separated list of input file paths or glob pattern |
| `template` | Optional | Template name to use (defaults to system default) |
| `rewrite_percent` | Optional | Rewrite percentage (0 = no rewrite) |
| `generate_preface` | Optional | yes/no (default: yes) |
| `generate_acknowledgement` | Optional | yes/no (default: yes) |
| `output_formats` | Optional | Comma-separated: epub, docx, pdf (default: epub) |

Column names above are defaults — all are remappable via config.

---

## 8. Template System

### 8.1 Design Principles

- Templates control **styling only**, never content logic
- Clean separation: pipeline produces structured content → template applies visual styling
- Templates are directories containing CSS, font files, and layout config
- Swapping a template = pointing config to a different directory

### 8.2 Template Contents

```
templates/
  academic/
    styles.css          # EPUB/HTML styling
    print.css           # PDF/print-specific overrides
    docx_reference.docx # Reference doc for Pandoc DOCX styling
    config.yaml         # Template metadata and layout rules
    fonts/              # Embedded fonts
  modern/
    ...same structure...
```

### 8.3 Template Config (`config.yaml`)

```yaml
name: "Academic"
description: "Traditional academic publishing style"

typography:
  body_font: "Crimson Text"
  heading_font: "Source Sans Pro"
  body_size: "11pt"
  line_height: 1.5

page_geometry:
  trim_size: "6x9in"
  margins:
    top: "0.75in"
    bottom: "0.75in"
    inner: "0.875in"
    outer: "0.625in"

front_matter:
  title_page_alignment: "center"
  copyright_font_size: "9pt"

media_rules:
  max_image_width: "100%"
  figure_caption_style: "italic"

tables:
  border_style: "grid"
  border_width: "0.25pt"
  header_background: "#f0f0f0"
```

### 8.4 Minimum Shipped Templates

1. **Academic** — traditional scholarly publishing (serif fonts, formal layout, footnotes)
2. **Modern** — clean contemporary style (sans-serif headings, generous whitespace, minimal ornamentation)

---

## 9. Architecture

### 9.1 High-Level Pipeline

```
Per-file (parallel):                   Per-book (sequential):
Input Files ──→ Ingestion ──→ Normalize ──→ Assemble ──→ AI ──→ Structure ──→ Export
     │              │             │             │          │         │           │
  (OCR, PDF,    (format-     (clean HTML    (merge all (rewrite, (title page, (EPUB,
   HTML, DOCX,   specific     + protected    articles   generate  copyright,   DOCX,
   EPUB, MD,     parsers)     blocks)        into one   titles    TOC)         PDF)
   TXT, scans)                               book)      from ALL
                                                        articles)
```

### 9.2 Module Breakdown

| Module | Responsibility |
|---|---|
| **Ingestion** | Read each input format, extract content, detect format type |
| **OCR** | Convert scanned images/PDFs to text (Tesseract, replaceable) |
| **Normalization** | Convert all inputs to clean semantic HTML with protected blocks |
| **Assembly** | Merge multiple articles into one book; order chapters; deduplicate assets |
| **AI Processing** | Generate front-matter, rewrite content, generate titles (from all article titles) |
| **Structure Builder** | Assemble book sections in correct order (conditional: preface/ack only if generated) |
| **Export** | Render final output in EPUB, DOCX, high-quality digital PDF |
| **Metadata** | Read and validate Excel metadata; strip author credentials |
| **Templates** | Load and apply styling configuration |
| **Jobs** | Subprocess worker, job state persistence, progress tracking |
| **API** | REST endpoints for triggering jobs and checking status |
| **UI** | Simple web interface for upload/download |

### 9.3 Intermediate Representation

All content is normalized to **clean semantic HTML** before any processing:

```html
<article data-source="chapter-1.pdf" data-type="chapter">
  <h1>Chapter Title</h1>
  <p>Paragraph text...</p>
  <table class="data-table">
    <thead>...</thead>
    <tbody>...</tbody>
  </table>
  <figure>
    <img src="fig1.png" alt="..." />
    <figcaption>Figure 1: Description</figcaption>
  </figure>
</article>
```

This HTML is the single format that all downstream modules consume. Ingestion modules are responsible for producing it; export modules are responsible for rendering it.

### 9.4 Component Replaceability

The following components are designed as pluggable interfaces:

| Component | Interface | Default Implementation |
|---|---|---|
| OCR Engine | `BaseOCREngine` | Tesseract |
| AI Provider | `BaseAIProvider` | Claude (Anthropic) |
| Export Format | `BaseExporter` | EPUB, DOCX, PDF |
| Ingestion Format | `BaseIngester` | One per input format |

New implementations register via config — no code changes to the pipeline.

---

## 10. Technical Stack

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Ecosystem for document processing, AI, OCR |
| Web Framework | FastAPI | Async, fast, auto-docs, production-ready |
| OCR | Tesseract (pytesseract) | Open-source, mature, replaceable |
| PDF Processing | PyMuPDF (fitz) | Fast, reliable text/image extraction |
| Document Conversion | Pandoc (pypandoc) | Industry standard for format conversion |
| EPUB Generation | ebooklib + Calibre (polish) | ebooklib for control, Calibre for polish/compatibility |
| DOCX Generation | python-docx + Pandoc | Fine control over Word output + table borders |
| PDF Generation | WeasyPrint | Free, CSS-based, good quality |
| Equation Rendering | MathML + matplotlib (image fallback) | Cross-format equation support |
| AI | anthropic SDK / openai SDK | Configurable provider |
| Excel Reading | openpyxl | Standard .xlsx reading |
| Task Queue (MVP) | Subprocess worker + file-based state | Survives restarts, no infra needed |
| Task Queue (Phase 2) | Celery + Redis | Multi-user, horizontal scaling |
| Config | YAML (PyYAML) | Human-readable, standard |
| Testing | pytest | Standard Python testing |
| Containerization | Docker + docker-compose | Reproducible deployment |

---

## 11. API Endpoints

### 11.1 Job Management

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/jobs` | Create a new conversion job (multipart upload) |
| `GET` | `/api/v1/jobs` | List all jobs with status |
| `GET` | `/api/v1/jobs/{id}` | Get job details and progress |
| `GET` | `/api/v1/jobs/{id}/download` | Download completed output files |
| `DELETE` | `/api/v1/jobs/{id}` | Cancel a running job |

### 11.2 Batch Management

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/batches` | Upload Excel + files → create multiple jobs (one per Excel row) |
| `GET` | `/api/v1/batches/{id}` | Batch-level progress across all books |

### 11.3 Configuration

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/templates` | List available templates |
| `GET` | `/api/v1/config` | Get current system configuration |

### 11.4 Health

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |

---

## 12. Content Rules

### 12.1 Author Names

- Only names are included — **never** designations, institutions, or affiliations
- System must strip these if present in metadata

### 12.2 Copyright Page

- Template-based with variable replacement
- Variables: `{isbn}`, `{eisbn}`, `{year}`, `{publisher_name}`, `{publisher_address}`, `{publisher_email}`
- Template file is externally editable

### 12.3 Table Formatting (Mandatory)

All tables across all output formats must:

- Have **grid borders** (all cells bordered)
- Use **hairline thickness** (~0.25pt)
- Render consistently in EPUB, DOCX, and PDF
- Preserve header row distinction

---

## 13. Error Handling

| Scenario | Behavior |
|---|---|
| Unsupported file type | Log error, skip file, continue batch |
| OCR failure on single file | Log error, skip file, continue batch |
| AI API failure | Retry 3x with exponential backoff; if still failing, skip AI features for that file and log |
| Corrupt/unreadable file | Log error with details, skip, continue |
| Missing required metadata | Reject the row, log which fields are missing, continue with other rows |
| Export failure for one format | Log error, continue with other formats |
| Batch completion | Generate summary report: succeeded, failed, skipped (with reasons) |

The system **never crashes the entire batch** due to a single file failure.

---

## 14. Performance Requirements

| Metric | Target |
|---|---|
| Batch size | 50–100 files minimum |
| Large files | Must not crash; process with bounded memory |
| Concurrent processing | MVP: file-level parallelism (configurable, default 4 concurrent files); Phase 2: Celery workers |
| OCR throughput | Async processing; don't block other conversions |
| Timeout | Configurable per-file timeout (default: 5 minutes) |

---

## 15. UI Requirements (MVP)

Simple web interface with:

1. **Upload area** — drag-and-drop for manuscript files + Excel metadata
2. **Options panel** — select: rewrite %, generate content (yes/no), output formats, template
3. **Job list** — shows all jobs with status (queued / processing / done / failed)
4. **Download** — download output files when job completes
5. **Error log** — view errors for failed files

No authentication in MVP. Single-user assumed.

---

## 16. Testing Requirements

### 16.1 Unit Tests

- Each ingestion module: valid input produces correct intermediate HTML
- Each export module: valid intermediate HTML produces valid output
- Metadata reader: correct parsing, missing field handling, column remapping
- Template loader: config parsing, CSS loading, font embedding
- AI module: prompt construction, response parsing (mocked API)

### 16.2 Integration Tests

- End-to-end: HTML → EPUB, DOCX, PDF
- End-to-end: Markdown → EPUB, DOCX, PDF
- End-to-end: TXT → EPUB, DOCX, PDF
- End-to-end: DOCX → EPUB
- End-to-end: PDF (digital) → EPUB
- End-to-end: EPUB → DOCX, PDF
- Batch: Multiple files with Excel metadata → all outputs

### 16.3 Validation Tests

- EPUB output validates against epubcheck
- DOCX output opens correctly in Word/LibreOffice
- PDF output is valid, well-formed, with embedded fonts and correct page geometry
- Tables render with correct borders in all formats

---

## 17. Project Structure

```
bookforge/
├── README.md
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── config/
│   ├── default.yaml          # Default system config
│   ├── columns.yaml          # Excel column mapping
│   └── prompts/
│       ├── title.txt         # AI prompt for title generation
│       ├── preface.txt       # AI prompt for preface
│       ├── acknowledgement.txt
│       └── rewrite.txt       # AI prompt for content rewriting
├── bookforge/
│   ├── __init__.py
│   ├── main.py               # FastAPI app
│   ├── core/
│   │   ├── pipeline.py       # Main orchestrator
│   │   ├── models.py         # Data models (Pydantic)
│   │   ├── config.py         # Config loader
│   │   └── registry.py       # Plugin registry
│   ├── ingestion/
│   │   ├── base.py           # Abstract ingester
│   │   ├── html.py
│   │   ├── markdown.py
│   │   ├── txt.py
│   │   ├── docx.py
│   │   ├── pdf.py
│   │   ├── epub.py
│   │   └── ocr.py
│   ├── metadata/
│   │   ├── reader.py         # Excel metadata reader
│   │   └── validator.py      # Metadata validation
│   ├── ai/
│   │   ├── base.py           # Abstract AI provider
│   │   ├── anthropic.py      # Claude implementation
│   │   ├── openai.py         # OpenAI implementation
│   │   ├── generator.py      # Content generation logic
│   │   └── rewriter.py       # Content rewriting logic
│   ├── structure/
│   │   ├── builder.py        # Book structure assembler
│   │   └── components.py     # Title page, copyright, etc.
│   ├── normalization/
│   │   ├── normalizer.py     # Main normalizer
│   │   ├── html_cleaner.py   # Strip non-semantic elements
│   │   ├── structure_detector.py
│   │   ├── equation_detector.py  # Detect/protect equations
│   │   └── table_standardizer.py
│   ├── assembly/
│   │   ├── assembler.py      # Merge articles → one book (Stage 3)
│   │   ├── ordering.py       # Article ordering logic
│   │   └── deduplicator.py   # Asset dedup, block renumbering
│   ├── export/
│   │   ├── base.py           # Abstract exporter
│   │   ├── epub.py
│   │   ├── docx.py
│   │   ├── pdf.py
│   │   ├── calibre_polish.py     # Optional EPUB polishing
│   │   ├── docx_table_borders.py # Hairline grid borders for DOCX
│   │   └── equation_renderer.py  # Cross-format equation rendering
│   ├── templates/
│   │   ├── loader.py         # Template loading logic
│   │   └── engine.py         # Template application engine
│   ├── jobs/
│   │   ├── manager.py        # Create, track, query jobs
│   │   ├── models.py         # Job, FileResult, BatchReport, JobProgress
│   │   ├── store.py          # File-based store (MVP); DB adapter (Phase 2)
│   │   └── worker.py         # Subprocess worker with progress tracking
│   ├── api/
│   │   ├── routes.py         # REST API endpoints
│   │   └── schemas.py        # Request/response Pydantic schemas
│   ├── ui/
│   │   └── static/           # Simple frontend (HTML/CSS/JS)
│   └── cli.py                # CLI entry point (Typer)
├── templates/
│   ├── academic/
│   │   ├── config.yaml
│   │   ├── styles.css
│   │   ├── print.css
│   │   ├── docx_reference.docx
│   │   └── fonts/
│   └── modern/
│       └── ...same structure...
├── tests/
│   ├── conftest.py
│   ├── test_ingestion/
│   ├── test_export/
│   ├── test_ai/
│   ├── test_metadata/
│   ├── test_structure/
│   ├── test_templates/
│   └── test_integration/
├── samples/
│   ├── input/                # Sample input files for testing
│   └── output/               # Expected output samples
└── docs/
    ├── REQUIREMENTS.md       # This file
    ├── SETUP.md              # Installation guide
    ├── CONFIGURATION.md      # Config reference
    └── TEMPLATES.md          # How to create/modify templates
```

---

## 18. Configuration Reference

### 18.1 Main Config (`config/default.yaml`)

```yaml
# BookForge Configuration

pipeline:
  intermediate_format: "html"    # Internal representation
  temp_dir: "/tmp/bookforge"
  max_file_size_mb: 500
  per_file_timeout_seconds: 300
  max_concurrent_files: 4        # File-level parallelism
  max_memory_per_file_mb: 512

ocr:
  engine: "tesseract"
  language: "eng"
  dpi: 300
  max_concurrent_pages: 2        # OCR is CPU-heavy

ai:
  provider: "anthropic"          # or "openai"
  model: "claude-sonnet-4-6"
  max_tokens: 4096
  temperature: 0.7
  prompts_dir: "config/prompts"
  rate_limit_rpm: 60             # Requests per minute cap
  cost_limit_per_job_usd: 50.0   # Safety cap

export:
  default_formats: ["epub"]
  epub:
    version: "3.0"
    validate: true
    calibre_polish: true         # Use Calibre if installed
  docx:
    generate_toc: true
    headers_footers: true        # Page numbers, book title in header
  pdf:
    engine: "weasyprint"
    dpi: 300
    pdf_a: false                  # Phase 2: requires PrinceXML

templates:
  default: "academic"
  directory: "templates"

worker:
  mode: "subprocess"             # MVP: subprocess; Phase 2: celery
  state_dir: "data/jobs"         # File-based job state persistence
  cleanup_after_hours: 24        # Auto-delete temp files

metadata:
  columns_config: "config/columns.yaml"

logging:
  level: "INFO"
  file: "logs/bookforge.log"
  format: "json"                 # Machine-parseable structured logs
```

---

## 19. Phases

### Phase 1 — MVP

- All ingestion modules (HTML, MD, TXT, DOCX, PDF, OCR, EPUB)
- EPUB export (primary)
- DOCX export
- PDF export
- AI content generation (title, preface, acknowledgement)
- AI rewriting at configurable levels
- Excel metadata reading
- Template system with 2 templates
- Batch processing
- REST API
- Simple web UI
- Test suite
- Documentation including `docs/TEMPLATES.md` with all Jinja variables (ship-blocking — client provides their own copyright template)

### Phase 2 — Enhancements

- Advanced indexing / back-of-book index generation
- Multi-language support (OCR + AI)
- UI improvements (progress bars, preview)
- Authentication and multi-user support
- Cloud storage integration (S3, GCS)
- Webhook notifications on job completion
- KindleGen / KDP-specific output
- ONIX metadata export for distributors

---

## 20. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| OCR quality on complex layouts | Poor structure extraction | Fallback to manual structure hints; support pre-processed input |
| **OCR cannot reconstruct equations from scans** | Equations appear as garbled text in output | **Known limitation.** Tesseract treats equations as text/symbols — produces garbage like `E = mc2` or `∫ f(x)dx`. Documented in SETUP.md. Workaround: client provides digital source files for math-heavy content, or pre-processes scans with equation-aware OCR (e.g., Mathpix). |
| AI rewriting changes meaning | Incorrect content in published book | Human review step; confidence scoring; side-by-side diff |
| Table formatting inconsistency across formats | Different rendering in EPUB vs PDF | Format-specific CSS/styling; dedicated table tests per format |
| Large files cause memory issues | Crashes | File-backed assets; per-file memory limits; timeout |
| AI API rate limits | Slow batch processing | Rate limiter with token bucket; retry with backoff; cost cap per job |
| DOCX equations not editable in Word | Client expects editable math in Word | MVP uses image-rendered equations (look correct, print cleanly, but not editable). Phase 2: OMML for editable equations. |

---

## 21. Success Criteria

The MVP is considered complete when:

1. All 7 input formats successfully convert to EPUB
2. EPUB, DOCX, and PDF outputs pass format validation
3. AI generates coherent titles, prefaces, and acknowledgements
4. AI rewriting produces structurally-intact content at ±25% level minimum
5. Tables render with correct grid borders in all output formats
6. Excel metadata drives book generation without any hardcoded fields
7. Template swap changes output styling without code changes
8. 50-file batch completes without crashing
9. All tests pass
10. Documentation covers setup, configuration, and template creation
