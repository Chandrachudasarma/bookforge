# BookForge — Setup Guide

## Live Instance

**Production:** https://bookforge.finwiser.org
- 3 sample jobs with downloadable EPUBs pre-loaded
- Creating jobs requires credentials: `demo` / password from admin
- Max 3 user-created jobs per instance
- AI powered by OpenAI GPT-4o ($1/job cost cap)

## System Requirements

- Python 3.11+
- System dependencies (for full functionality):

| Dependency | Required for | Install |
|---|---|---|
| Tesseract OCR | Scanned image/PDF ingestion | `brew install tesseract` (macOS) / `apt install tesseract-ocr` |
| Pandoc | Markdown ingestion (GFM) | `brew install pandoc` (macOS) / `apt install pandoc` |
| WeasyPrint + Pango | PDF export | `brew install pango` (macOS) / `apt install libpango-1.0-0 libpangocairo-1.0-0` |
| Calibre | EPUB polishing (optional) | `brew install --cask calibre` (macOS) |

## Quick Start (Local Development)

```bash
# Clone and install
git clone https://github.com/Chandrachudasarma/bookforge.git && cd bookforge
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Configure AI provider
cat > config/local.yaml << 'EOF'
ai:
  provider: "openai"
  api_key: "sk-your-key"
  model: "gpt-4o"
EOF

# Run tests (no AI calls — mocked)
pytest tests/ -v

# Convert a single file
bookforge convert input.html --format epub docx

# Start the web server
BOOKFORGE_ENV=development bookforge serve --port 8000
# Open http://localhost:8000 (Swagger docs at /docs in dev mode)
```

## Docker Deployment

```bash
# Build and run
docker-compose up -d --build

# Generate sample jobs
docker-compose exec app python scripts/generate_samples.py

# Verify
curl http://localhost:8000/health
```

The Docker image uses a multi-stage build — runtime image contains only installed packages, not source code.

## Production Deployment (Oracle Cloud)

BookForge runs on the same server as Finwiser but is fully isolated:

| | Finwiser | BookForge |
|---|---|---|
| Directory | `/srv/finwiser/platform/` | `/srv/bookforge/` |
| Port | 5001 | 9090 |
| Process | PM2 `finwiser-prod` | Docker container |
| Domain | api.finwiser.org | bookforge.finwiser.org |

### Deploy steps

```bash
ssh finwiser-prod
cd /srv/bookforge
git pull

# Create/update config
cat > config/local.yaml << 'EOF'
auth:
  demo_password: "your-password"
ai:
  provider: "openai"
  api_key: "sk-your-key"
  model: "gpt-4o"
  cost_limit_per_job_usd: 1.0
  rate_limit_rpm: 10
EOF

# Rebuild and restart
sudo docker compose up -d --build

# Regenerate sample jobs (if needed)
sudo docker compose exec app python -c "..."  # see scripts/generate_samples.py
```

### Nginx config

```nginx
server {
    listen 80;
    server_name bookforge.finwiser.org;
    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:9090;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

SSL is handled by Cloudflare (DNS proxied).

## Configuration

### Config Layers (merge order)

1. `config/default.yaml` — base defaults (committed)
2. `config/local.yaml` — local overrides (git-ignored, contains secrets)
3. Environment variables — `BOOKFORGE_*` prefix
4. Job-level overrides — per-job config from API/Excel

### Key Settings

```yaml
# config/local.yaml
auth:
  demo_password: ""          # Lock POST/DELETE endpoints

ai:
  provider: "openai"          # or "anthropic"
  api_key: ""                 # API key (never commit)
  model: "gpt-4o"             # or "claude-sonnet-4-6"
  cost_limit_per_job_usd: 1.0 # Per-job cost cap
  rate_limit_rpm: 10           # API calls per minute
  max_chunk_tokens: 3000       # Rewrite chunk size
```

### Environment Variables

```bash
BOOKFORGE_AI_API_KEY=your-key
BOOKFORGE_AI_PROVIDER=openai
BOOKFORGE_LOG_LEVEL=INFO
BOOKFORGE_ENV=development      # Enables Swagger docs at /docs
```

## Security

| Feature | Status |
|---|---|
| Basic auth on POST/DELETE | Enabled (username: `demo`) |
| Per-user job limit | 3 max (excludes sample jobs) |
| Swagger/OpenAPI docs | Disabled in production |
| Error path stripping | Filesystem paths removed from API errors |
| File download traversal | Path traversal blocked (403) |
| Docker multi-stage build | Source code not in runtime image |
| Config secrets | `local.yaml` git-ignored |

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

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/jobs` | Required | Create job (upload files) |
| GET | `/api/v1/jobs` | Open | List all jobs |
| GET | `/api/v1/jobs/{id}` | Open | Job status + progress |
| DELETE | `/api/v1/jobs/{id}` | Required | Cancel a job |
| GET | `/api/v1/jobs/{id}/download/{file}` | Open | Download output |
| GET | `/api/v1/templates` | Open | List templates |
| GET | `/api/v1/config` | Required | Pipeline config |
| GET | `/health` | Open | Dependency check |

## Known Limitations

### OCR Equation Limitation

Tesseract OCR cannot reconstruct mathematical equations from scanned images. The OCR produces garbled text for math notation. This is by design — we do not attempt to fix OCR equation output.

**Recommendation:** For math-heavy content, use digital source files (DOCX, HTML with MathML) rather than scanned PDFs.

### PDF Table Extraction

Tables in PDFs are extracted using PyMuPDF's `find_tables()` which detects tabular layouts. Complex tables with irregular merged cells may not extract perfectly. The extracted tables are tagged as protected blocks and survive AI rewriting.

### AI Rewriting

- The AI never sees protected blocks (tables, equations) — they're split out before rewriting and stitched back in afterward
- GPT-4o tends to expand content more than requested (asked for 30%, may produce 100%)
- Cost is capped per job ($1.0 default) to prevent runaway spending

### WeasyPrint Font Resolution

WeasyPrint resolves font `url()` relative to `base_url`. The template system sets this automatically. If fonts fail to load, WeasyPrint falls back to system fonts silently.

### Calibre Polish

Optional. If not installed, EPUB output is still valid but some e-reader compatibility improvements are skipped.
