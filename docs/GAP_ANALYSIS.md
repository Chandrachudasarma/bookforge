# BookForge — Gap Analysis: Client Spec vs Architecture

**Date:** 2026-04-05
**Status:** All phases implemented and deployed. See IMPLEMENTATION.md for final status.

Systematic comparison of every client requirement against our architecture.
Rating: COVERED / PARTIAL / GAP / OVER-ENGINEERED

---

## 1. Input Formats

| Client Requirement | Architecture Status | Notes |
|---|---|---|
| Scanned files (OCR) | COVERED | `OcrIngester` + `BaseOCREngine` + Tesseract impl |
| PDF (scanned vs digital detection) | COVERED | `PdfIngester` with auto-detection + OCR routing |
| HTML | COVERED | `HtmlIngester` |
| Word (DOCX) | COVERED | `DocxIngester` |
| EPUB → Word/PDF | COVERED | `EpubIngester` for reverse conversion |
| Markdown | COVERED | `MarkdownIngester` — client didn't ask for this but first message did |
| Plain text (TXT) | COVERED | `TxtIngester` — client didn't ask for this but first message did |

**Verdict:** All input formats covered. MD and TXT are bonuses from the first brief.

---

## 2. Output Formats

| Client Requirement | Architecture Status | Notes |
|---|---|---|
| EPUB — clean, compatible | COVERED | `EpubExporter` via ebooklib, EPUB 3.0 |
| DOCX — print-ready, with TOC | COVERED | `DocxExporter` via python-docx + Pandoc |
| PDF — high-quality digital | COVERED | `PdfExporter` via WeasyPrint. Press-quality (bleed/CMYK/PDF-A) is Phase 2 via PrinceXML. |

**Verdict:** All output formats covered.

---

## 3. Core Features (Section 4 of client spec)

### 4.1 Batch Processing

| Requirement | Status | Notes |
|---|---|---|
| Upload multiple files | COVERED | Job model accepts list of files |
| Process via queue system | COVERED | MVP: BackgroundTasks; Phase 2: Celery |
| 50-100 files per batch | COVERED | Per-file isolation, no batch-level crash |

### 4.2 Excel-Based Metadata Input

| Requirement | Status | Notes |
|---|---|---|
| Read Excel file | COVERED | `metadata/reader.py` via openpyxl |
| Dynamic column mapping | COVERED | `config/columns.yaml` — all column names configurable |
| Missing field handling | COVERED | `metadata/validator.py` — graceful defaults |

### 4.3 AI-Generated Content

| Requirement | Status | Notes |
|---|---|---|
| Book Title (from article titles) | COVERED | `ai/generator.py` + `config/prompts/title.txt` |
| Preface | COVERED | `ai/generator.py` + `config/prompts/preface.txt` |
| Acknowledgement | COVERED | `ai/generator.py` + `config/prompts/acknowledgement.txt` |

### 4.4 AI Rewriting

| Requirement | Status | Notes |
|---|---|---|
| Expand/reduce ±10% to ±100% | COVERED | `ai/rewriter.py` — configurable percentage |
| Preserve structure | COVERED | Chunk at heading boundaries, skip tables/figures |
| Avoid plagiarism | PARTIAL | **Prompt-dependent** — we configure prompts to instruct this, but no plagiarism detection tool integrated |
| Not modify equations/tables | COVERED | Rewriter skips `<table>`, `<figure>`, math markup |

> **GAP: Plagiarism detection.** Client says "avoid plagiarism" — our architecture relies on AI prompt instructions only. No dedicated plagiarism checker (like Turnitin API or Copyscape) is integrated. **Risk:** Client may expect a plagiarism score or verification step. **Recommendation:** Add as optional Phase 2 feature, or integrate a simple similarity check.

### 4.5 Table Formatting (MANDATORY)

| Requirement | Status | Notes |
|---|---|---|
| Grid borders | COVERED | Template `config.yaml` → `tables.border_style: "grid"` |
| Hairline thickness (~0.25pt) | COVERED | Template `config.yaml` → `tables.border_width: "0.25pt"` |
| Works in EPUB | COVERED | CSS in `styles.css` |
| Works in Word | PARTIAL | **Needs attention** — DOCX table borders require python-docx manipulation, not just CSS |
| Works in PDF | COVERED | CSS in `styles.css` + `print.css` via WeasyPrint |

> **GAP: DOCX table borders.** CSS doesn't control DOCX table styling. The `docx_reference.docx` sets default styles, but per-table hairline borders need explicit python-docx code in the `DocxExporter`. Architecture should note this as a format-specific post-processing step.

### 4.6 Book Structure Generation

| Requirement | Status | Notes |
|---|---|---|
| Title Page (AI-generated title) | COVERED | `structure/front_matter.py` |
| Copyright Page (template-based) | COVERED | Jinja template in `templates/*/copyright.html.jinja` |
| Preface (AI-generated) | COVERED | `ai/generator.py` → `structure/builder.py` |
| Acknowledgement (AI-generated) | COVERED | Same |
| Table of Contents | COVERED | `structure/toc_generator.py` |
| Chapters (articles) | COVERED | Main content in `BookManifest.sections` |

---

## 4. Content Rules (Section 5 of client spec)

### Author Names

| Requirement | Status | Notes |
|---|---|---|
| Only names — no designations | COVERED | `metadata/validator.py` strips credentials |
| No institutions/affiliations | COVERED | Same |

### Copyright Page

| Requirement | Status | Notes |
|---|---|---|
| Template-based | COVERED | `copyright.html.jinja` |
| Replace ISBN, eISBN, year, etc. | COVERED | Jinja variables from `BookMetadata` |
| "Template will be provided" | PARTIAL | **Client will provide their own template** — architecture supports this (just drop a new Jinja file), but we should document the expected variables clearly |

> **NOTE:** Client says "template will be provided." Our architecture supports custom templates, but we need a clear spec of what variables are available for template authors.

### Title Page

| Requirement | Status | Notes |
|---|---|---|
| AI-generated title | COVERED | `ai/generator.py` |
| Editor/Author from Excel | COVERED | `BookMetadata.authors` from Excel |

---

## 5. Technical Requirements (Section 6 of client spec)

### Preferred Stack

| Requirement | Status | Notes |
|---|---|---|
| Python (FastAPI preferred) | COVERED | Exact match |
| Tesseract for OCR | COVERED | Default OCR engine |
| Pandoc for conversion | COVERED | Used in DOCX export + Markdown ingestion |
| Calibre | ~~GAP~~ COVERED | **FIXED:** `calibre_polish.py` as optional post-processing step. Auto-detected at startup. |

### Architecture (MANDATORY)

| Requirement | Status | Notes |
|---|---|---|
| Modular (separate OCR/conversion/AI/output) | COVERED | 5-stage pipeline with separate packages |
| Config-driven (no hardcoding) | COVERED | YAML config + external prompts + column mapping |
| Scalable (batch, future API, multi-user) | COVERED | Job model + API + Phase 2 Celery path |
| Replaceable OCR engine | COVERED | `BaseOCREngine` interface |
| Replaceable AI provider | COVERED | `BaseAIProvider` interface |

---

## 6. UI Requirements (Section 7 of client spec)

| Requirement | Status | Notes |
|---|---|---|
| Upload files | COVERED | API endpoint + static UI |
| Upload Excel | COVERED | API endpoint |
| Select rewrite % | COVERED | Job config option |
| Select generate content yes/no | COVERED | Job config option |
| Download output | COVERED | API download endpoint |

---

## 7. Error Handling (Section 9 of client spec)

| Requirement | Status | Notes |
|---|---|---|
| Skip problematic files | COVERED | File-level try/except |
| Continue batch processing | COVERED | One failure never kills batch |
| Provide error report | COVERED | `BatchReport` with per-file status |

---

## 8. Performance (Section 10 of client spec)

| Requirement | Status | Notes |
|---|---|---|
| 50-100 files per batch | COVERED | Sequential processing with per-file isolation |
| Should not crash on large files | COVERED | Configurable timeout (5 min default) |

> **PARTIAL: Memory bounded processing.** Architecture mentions "bounded memory" in requirements but doesn't specify *how*. For large PDFs (500MB+), we need streaming extraction rather than loading everything into memory. **Recommendation:** Add a `max_file_size_mb` check at ingestion and stream-process PDFs page-by-page.

---

## 9. Deliverables (Section 11 of client spec)

| Requirement | Status | Notes |
|---|---|---|
| Working application | COVERED | FastAPI app + CLI |
| Source code (fully commented) | PARTIAL | Architecture doesn't mandate docstrings — **need JSDoc-style Python docstrings on all public functions** |
| Setup instructions | COVERED | `docs/SETUP.md` planned |
| Config guide | COVERED | `docs/CONFIGURATION.md` planned |
| Sample outputs | COVERED | `samples/output/` directory |

---

## 10. Mandatory Development Conditions (Section 12 — "VERY IMPORTANT")

| Requirement | Status | Notes |
|---|---|---|
| NOT hardcode Excel structure | COVERED | `config/columns.yaml` |
| NOT hardcode templates | COVERED | Template directories, swappable |
| NOT hardcode prompts | COVERED | `config/prompts/*.txt` |
| Fields changeable without code edits | COVERED | All config-driven |
| Prompts modifiable easily | COVERED | Plain text files |
| Templates replaceable | COVERED | Directory-based, registered by name |
| Clean and readable code | INTENT | Depends on implementation |
| Modular | COVERED | 10 sub-packages, clear boundaries |
| Future scalable | COVERED | Plugin interfaces, Phase 2 path |

---

## Summary of All Gaps — Final Status

### Round 1: Critical Gaps — ALL RESOLVED

| # | Gap | Resolution |
|---|---|---|
| 1 | ~~Calibre not included~~ | **FIXED:** `calibre_polish.py` as optional post-processing. Auto-detected. |
| 2 | ~~DOCX table borders~~ | **FIXED:** `docx_table_borders.py` with python-docx cell manipulation. |
| 3 | ~~Equation handling~~ | **FIXED:** `equation_detector.py` + `bf-protected` placeholders + `equation_renderer.py`. |

### Round 2: Additional Gaps — ALL RESOLVED

| # | Gap | Resolution |
|---|---|---|
| 4 | ~~PyMuPDF missing from dependencies~~ | **FIXED:** Added Python library dependency table to ARCHITECTURE.md §14. |
| 5 | ~~Celery/Redis conflict~~ | **FIXED:** REQUIREMENTS.md updated: subprocess worker for MVP, Celery for Phase 2. Config updated. Both docs now agree. |
| 6 | ~~PNG/JPEG/BMP scans not mentioned~~ | **FIXED:** OcrIngester diagram now shows all 4 formats. Tesseract dep notes all formats. |
| 7 | ~~DOCX headers/footers missing~~ | **FIXED:** `_apply_headers_footers()` added to DocxExporter design with python-docx code. |
| 8 | ~~Folder structure divergence~~ | **FIXED:** REQUIREMENTS.md §17 synced to match ARCHITECTURE.md (queue/ → jobs/, added api/, cli.py). |
| 9 | ~~Worker count config unclear~~ | **FIXED:** Config shows `max_concurrent_files: 4` for MVP. Clarified MVP vs Phase 2. |
| 10 | ~~GFM Markdown not specified~~ | **FIXED:** MarkdownIngester notes `--from gfm`. Pandoc dep notes GFM. |
| 11 | ~~TXT chapter break strategy missing~~ | **FIXED:** 5 heuristic rules documented + optional AI structure inference. |

### Round 3: Scalability Gaps — ALL RESOLVED

| # | Gap | Resolution |
|---|---|---|
| 12 | ~~BackgroundTasks won't survive batches~~ | **FIXED:** Subprocess worker with file-based state persistence. Survives restarts. |
| 13 | ~~No progress tracking~~ | **FIXED:** `JobProgress` model with per-file tracking. Status written to disk, polled by API. |
| 14 | ~~No file-level parallelism~~ | **FIXED:** `asyncio.Semaphore(max_concurrent_files)` for 4x throughput. |
| 15 | ~~Assets stored as bytes in memory~~ | **FIXED:** `Asset.file_path: Path` instead of `Asset.data: bytes`. File-backed. |

### Round 4: Architecture Review Gaps — ALL RESOLVED

| # | Gap | Resolution |
|---|---|---|
| 16 | ~~Batch orchestration driver unspecified~~ | **FIXED:** Added §7b "Batch Orchestration" with full flow: Excel → metadata/reader → metadata/validator → jobs/manager → batch tracker. New `POST /api/v1/batches` endpoint. |
| 17 | ~~Author name stripping not addressed~~ | **FIXED:** `strip_author_credentials()` function documented in §7b with 5 stripping rules + examples. Runs in metadata/validator.py. |
| 18 | ~~EPUB equations default to MathML (Kindle-incompatible)~~ | **FIXED:** EPUB now defaults to **image-rendered equations**. MathML is opt-in via `export.epub.equation_mode: "mathml"`. Kindle/KDP gets images by default. |
| 19 | ~~DOCX OMML underestimated~~ | **FIXED:** Explicitly flagged as HIGH IMPLEMENTATION RISK. MVP uses image fallback. OMML conversion chain documented for Phase 2 (LaTeX → MathML → XSLT → OMML). |
| 20 | ~~AI rewriter has no token budget~~ | **FIXED:** Added hierarchical splitting: token count → if over budget, split at `<p>` boundaries into ~3000-token chunks → rewrite with overlapping context → reassemble. Config: `ai.max_chunk_tokens`, `ai.context_overlap_tokens`. |
| 21 | ~~Progress tracking has no polling spec~~ | **FIXED:** MVP: 2-second polling via `GET /api/v1/jobs/{id}`. Phase 2: SSE via `/api/v1/jobs/{id}/stream`. Documented for frontend developer. |
| 22 | ~~Generate preface/ack skip path not modeled~~ | **FIXED:** Stage 3 diagram now shows each sub-feature as independently toggleable (`config.generate_preface: true/false`, etc.). Stage skipped only when ALL AI features are off. |

### Round 5: Final Review — ALL RESOLVED

| # | Gap | Resolution |
|---|---|---|
| 23 | ~~Batch endpoints missing from REQUIREMENTS.md API section~~ | **FIXED:** Added §11.2 Batch Management with `POST /api/v1/batches` and `GET /api/v1/batches/{id}`. Both docs now agree. |
| 24 | ~~AI chunk context could cause duplicate content~~ | **FIXED:** Clarified `system_context` is read-only (passed in system prompt, not rewritten). Uses original text tail as context, not rewritten text. Prompt template explicitly says "Do NOT rewrite context." |
| 25 | ~~Template variable docs marked optional but is ship-blocking~~ | **FIXED:** Upgraded M4 to MVP exit criterion. Added to REQUIREMENTS.md Phase 1 deliverables as ship-blocking. |
| 26 | ~~Tesseract equation blindness not user-visible~~ | **FIXED:** Added to REQUIREMENTS.md §20 Risks table with explicit description and workaround (provide digital source or use Mathpix). Will also go in SETUP.md. |
| 27 | ~~Stage 4 assembles all 8 sections unconditionally~~ | **FIXED:** Stage 4 diagram now shows conditional inclusion. `build_manifest()` code shows: preface/ack included only if generated, index only if configured. None→omit logic is explicit. |

### Round 6: Architect's Final Review — RESOLVED

| # | Gap | Resolution |
|---|---|---|
| 28 | ~~Multi-article-to-single-book assembly (R2)~~ | **FIXED:** Added Stage 3 (Assemble) to pipeline. 6-stage pipeline now: Ingest → Normalize → **Assemble** → AI → Structure → Export. Stages 1–2 per-file (parallel), Stage 3 aggregates, Stages 4–6 per-book. `AssembledBook` data model carries `article_titles[]` for AI title generation. New `assembly/` package with assembler.py, ordering.py, deduplicator.py. |
| 29 | ~~WeasyPrint "press-quality" overstated (R1)~~ | **FIXED:** Downgraded to "high-quality digital PDF" everywhere. WeasyPrint limitations (no bleed, no CMYK, no PDF/A) explicitly documented. `pdf.engine: "prince"` config stub for Phase 2. |

### Remaining (Medium — acceptable for MVP delivery)

| # | Gap | Status | Notes |
|---|---|---|---|
| M1 | Plagiarism verification | Phase 2 | Prompt-based only in MVP. Similarity scoring deferred. |
| M2 | Equations in OCR scans | Known limitation | Tesseract can't reconstruct equations. Documented in REQUIREMENTS.md §20 Risks. |
| M3 | Docstring mandate | Implementation rule | Every public class/method gets a docstring. Enforced during code review. |
| M4 | Copyright template variable reference | **MVP exit criterion** | `docs/TEMPLATES.md` MUST list all available Jinja variables with types and examples. Client provides their own copyright template — they can't use it without this doc. Ship-blocking. |
| M5 | DOCX editable equations (OMML) | Phase 2 | MVP uses image fallback. OMML is a Phase 2 enhancement. |
| M6 | Press-quality PDF (bleed/CMYK/PDF-A) | Phase 2 | Requires PrinceXML ($3,800/yr). Config stub ready: `pdf.engine: "prince"`. |

### Docs Alignment

Both REQUIREMENTS.md and ARCHITECTURE.md are now fully synchronized:
- Same folder structure
- Same tech stack (subprocess worker for MVP, Celery Phase 2)
- Same config format (with parallelism, resource limits, structured logging)
- Same dependency list
