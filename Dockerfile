# Stage 1: Build — install dependencies and compile
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml .
COPY bookforge/ bookforge/
RUN pip install --no-cache-dir --prefix=/install .


# Stage 2: Runtime — lean image with only installed package
FROM python:3.11-slim

# System dependencies for OCR, Pandoc, PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    pandoc \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    libharfbuzz0b \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only installed packages from builder (no source .py files)
COPY --from=builder /install /usr/local

# Copy runtime assets only
COPY config/ config/
COPY templates/ templates/

RUN mkdir -p data/jobs logs

EXPOSE 8000

CMD ["uvicorn", "bookforge.main:app", "--host", "0.0.0.0", "--port", "8000"]
