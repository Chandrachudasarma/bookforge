# BookForge — Setup Guide

## System Requirements

- Python 3.11+
- System dependencies (for full functionality):

| Dependency | Required for | Install |
|---|---|---|
| Tesseract OCR | Scanned image/PDF ingestion | `brew install tesseract` (macOS) / `apt install tesseract-ocr` |
| Pandoc | Markdown ingestion (GFM) | `brew install pandoc` (macOS) / `apt install pandoc` |
| WeasyPrint + Pango | PDF export | `brew install pango` (macOS) / `apt install libpango-1.0-0 libpangocairo-1.0-0` |
| Calibre | EPUB polishing (optional) | `brew install --cask calibre` (macOS) |

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd bookforge
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env
# Edit .env with your Anthropic API key

# Run tests (no AI calls — mocked)
pytest tests/ -v --ignore=tests/test_integration

# Run integration tests
pytest tests/test_integration/ -v

# Convert a single file
bookforge convert samples/input/test.html --format epub docx

# Start the web server
bookforge serve --port 8000
# Open http://localhost:8000 in your browser
```

## Docker

```bash
# Build
docker build -t bookforge .

# Run
docker-compose up

# Access at http://localhost:8000
```

The Docker image includes all system dependencies (Tesseract, Pandoc, Pango).

## Configuration

### Config Layers (merge order)

1. `config/default.yaml` — base defaults (committed)
2. `config/local.yaml` — local overrides (git-ignored)
3. Environment variables — `BOOKFORGE_*` prefix
4. Job-level overrides — per-job config from API/Excel

### Key Environment Variables

```bash
BOOKFORGE_AI_API_KEY=your-anthropic-key    # Required for AI features
BOOKFORGE_AI_PROVIDER=anthropic            # "anthropic" (default) or "openai"
BOOKFORGE_DATA_DIR=data                    # Job storage directory
BOOKFORGE_LOG_LEVEL=INFO                   # DEBUG | INFO | WARNING
```

### Column Mapping

Excel column headers are mapped to internal fields via `config/columns.yaml`. Edit this file to match your spreadsheet without changing code:

```yaml
mappings:
  title: "Title"
  author_name: "Author"
  isbn: "ISBN"
  # ... see config/columns.yaml for all 17 fields
```

## CLI Commands

```bash
# Single file conversion
bookforge convert input.html -f epub docx -t academic

# Batch processing from Excel
bookforge batch metadata.xlsx --input-dir ./manuscripts/ --output-dir ./output/

# Start web server
bookforge serve --port 8000 --reload
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/jobs` | Create job (upload files) |
| GET | `/api/v1/jobs` | List all jobs |
| GET | `/api/v1/jobs/{id}` | Job status + progress |
| DELETE | `/api/v1/jobs/{id}` | Cancel a job |
| GET | `/api/v1/jobs/{id}/download/{file}` | Download output |
| GET | `/api/v1/templates` | List templates |
| GET | `/api/v1/config` | Pipeline config |
| GET | `/health` | Dependency check |

## Known Limitations

### OCR Equation Limitation

Tesseract OCR cannot reconstruct mathematical equations from scanned images. When processing scanned PDFs or images containing equations:

- The OCR produces garbled text for mathematical notation
- The equation detector will NOT detect these as equations (they're not in LaTeX/MathML format)
- The garbled text passes through to the output unchanged

**This is by design.** We do not attempt to "fix" OCR equation output because:
1. Heuristic cleanup would sometimes remove valid content
2. The correct solution is to use digital source files for math-heavy content
3. For scanned math content, use Mathpix or similar pre-processing before BookForge

**Recommendation to clients:** For books with significant mathematical content, always provide digital source files (DOCX, LaTeX, HTML with MathML) rather than scanned PDFs.

### WeasyPrint Font Resolution

WeasyPrint resolves `url()` in CSS relative to `base_url`. The template system sets `base_url` to the template directory automatically. If fonts fail to load:

1. Check that font files exist in `templates/{name}/fonts/`
2. Check that CSS `@font-face` uses `url('fonts/FontName.ttf')` (relative path)
3. WeasyPrint falls back to system fonts silently — no error is raised

### Calibre Polish

Calibre's `ebook-polish` is optional. If not installed:
- EPUB output is still valid
- Some e-reader compatibility improvements are skipped
- On macOS, BookForge checks both `PATH` and `/Applications/calibre.app/Contents/MacOS/`
