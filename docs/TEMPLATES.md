# BookForge — Template Reference

## Template Directory Structure

Each template is a directory under `templates/` with this layout:

```
templates/{name}/
  config.yaml              # Template metadata and typography settings (required)
  styles.css               # EPUB + PDF base stylesheet (required)
  print.css                # PDF-only overrides — @page rules, margins (optional)
  title_page.html.jinja    # Title page Jinja template (optional)
  copyright.html.jinja     # Copyright page Jinja template (optional)
  docx_reference.docx      # DOCX style reference document (optional)
  fonts/                   # Embedded TTF/OTF fonts (optional)
    FontName-Regular.ttf
    FontName-Bold.ttf
```

## Shipped Templates

| Name | Style | Font | Description |
|---|---|---|---|
| `academic` | Traditional scholarly | Crimson Text / Georgia (serif) | Justified text, text-indent paragraphs, formal headings, A5 print |
| `modern` | Contemporary | Helvetica Neue / Arial (sans-serif) | Left-aligned, no indent, bordered headings, generous whitespace |

## config.yaml Reference

```yaml
display_name: "Academic"           # Human-readable name for UI
description: "Traditional scholarly publishing style"
font_family: "'Crimson Text', Georgia, serif"
font_size: "11pt"
line_height: "1.5"
page_margins:
  top: "2cm"
  bottom: "2cm"
  left: "2.5cm"
  right: "2cm"
```

## Jinja Template Variables

All `.html.jinja` files have access to these variables from `BookMetadata`:

| Variable | Type | Example | Notes |
|---|---|---|---|
| `title` | string | `"Machine Learning in Medicine"` | Main title (before colon if subtitle present) |
| `subtitle` | string \| None | `"A Clinical Perspective"` | After colon in title, or None |
| `authors` | list[string] | `["Jane Smith", "John Doe"]` | Use `{{ authors \| join(", ") }}` |
| `isbn` | string \| None | `"978-0-1234-5678-0"` | Print ISBN |
| `eisbn` | string \| None | `"978-0-1234-5679-7"` | Electronic ISBN |
| `publisher_name` | string | `"Academic Press"` | |
| `publisher_address` | string \| None | `"123 Main St, City"` | |
| `publisher_email` | string \| None | `"info@press.com"` | |
| `year` | int | `2026` | Publication year |
| `language` | string | `"en"` | ISO 639-1 code |
| `cover_image` | Path \| None | | Cover image path |

**Jinja validation:** Templates are validated at load time. Any variable not in this list causes a `TemplateError` at startup, not at render time.

## CSS Conventions

### styles.css (EPUB + PDF base)

Applied to both EPUB and PDF output. Must be EPUB-safe CSS:

- Use `page-break-before: always` + `break-before: page` for chapter breaks (both legacy and modern)
- Tables use `border: 0.25pt solid #000` for hairline grid borders
- Protected equation images use `vertical-align: middle`
- Use the CSS classes from the pipeline:

| Class | Applied to | Purpose |
|---|---|---|
| `.bf-chapter` | `<section>` | Chapter container |
| `.bf-protected` | `<span>`, `<table>` | Protected blocks (equations, tables) |
| `.title-page` | `<div>` | Title page wrapper |
| `.copyright-page` | `<div>` | Copyright page wrapper |
| `.cover-page` | `<div>` | Cover page wrapper |
| `.toc` | `<div>` | Table of contents |
| `.equation` | `<img>` | Rendered equation images |

### print.css (PDF-only)

Applied via WeasyPrint on top of styles.css. Use for:
- `@page` rules (size, margins, running headers/footers)
- Page counters (`content: counter(page)`)
- Orphan/widow control
- Page-break avoidance for tables and figures

## Creating a Custom Template

1. Copy an existing template directory:
   ```bash
   cp -r templates/academic templates/my_template
   ```

2. Edit `config.yaml` with your settings

3. Modify `styles.css` for your design

4. Optionally add `print.css` for PDF-specific rules

5. Optionally add fonts to `fonts/` and reference them in CSS:
   ```css
   @font-face {
       font-family: 'MyFont';
       src: url('fonts/MyFont-Regular.ttf') format('truetype');
   }
   ```

6. Edit Jinja templates for front matter customization

7. Use the template:
   ```bash
   bookforge convert input.html --template my_template
   ```

## Template Selection

- **CLI:** `--template academic` or `--template modern`
- **API:** `config.template` field in the create job request
- **Excel batch:** `Template` column in the metadata sheet
- **Default:** `academic` (set in `config/default.yaml`)
