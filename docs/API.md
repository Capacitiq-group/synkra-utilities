# Synkra Business Utilities — API Reference

Stateless processing API. No accounts, no dashboard, no persistent storage.
Every endpoint takes a request, does the job, streams the result back, and
the temp files are deleted immediately after (background task on the
response, plus a periodic sweep as a backstop — see `app/core/cleanup.py`).

Base URL (example): `https://utilities-api.synkra.co.za/api/v1`

All endpoints are `multipart/form-data` for file uploads (field name is
always `file`) except the QR generator and email signature generator,
which take JSON.

---

## 1. QR Code Generator
`POST /qr/generate` — JSON body, returns image.

| Field | Type | Notes |
|---|---|---|
| `qr_type` | enum | `url`, `text`, `email`, `phone`, `whatsapp`, `wifi`, `vcard` |
| `output_format` | enum | `png` (default) or `svg` |
| `error_correction` | enum | `L`, `M` (default), `Q`, `H` |
| `size` | int 1–40 | box size, PNG only |
| `margin` | int 0–20 | |
| `fill_color` / `back_color` | hex string | |
| *type-specific fields* | | e.g. `value` for url/text, `wifi_ssid`/`wifi_password`/`wifi_encryption`, `vcard_name`/`vcard_org`/etc. See `app/routers/qr.py::QRRequest` for the full field list per type. |

Response: `image/png` or `image/svg+xml`, streamed directly — no JSON wrapper.

---

## 2. Image Compressor
`POST /image/compress` — form-data `file` + query `quality` (1–95, default 75).

Accepts JPG/PNG/WEBP. Returns the compressed image with headers:
`X-Original-Size-Bytes`, `X-Compressed-Size-Bytes`, `X-Size-Saved-Percent`
— use these to show the "before/after" UI the spec calls for without a
second round trip.

## 3. Image Converter
`POST /image/convert` — form-data `file` + query `target_format` (`jpg`|`png`|`webp`).

## 4. File Compressor
`POST /file/compress` — form-data `file` + query `image_quality` (1–95, default 70).
Accepts PDF or DOCX. Same size-saved headers as the image compressor.
**Images should go to `/image/compress` instead** — this endpoint 400s on them.

## 5. File Converter
- `POST /file/convert/pdf-to-images` — form-data `file` + query `dpi` (72–300). Returns a `.zip` of PNGs, one per page.
- `POST /file/convert/csv-to-xlsx` — form-data `file`. Returns `.xlsx`.
- `POST /file/convert/docx-to-pdf` — **disabled by default**, returns `501`. See "DOCX → PDF" below before turning it on.

## 6. Background Remover
`POST /image/remove-background` — form-data `file`. Returns transparent PNG.
Rate-limited harder than the rest (`RATE_LIMIT_HEAVY`, default 10/hour) —
it's the most CPU-expensive endpoint in the service.

## 7. CSV Cleaner
`POST /csv/clean` — form-data `file` + JSON `options` field (as a form field, JSON-encoded string, or send as multipart with a `options` part — FastAPI will parse either).

```json
{
  "operations": ["trim_whitespace", "remove_blank_rows", "remove_duplicates",
                  "standardise_headers", "validate_emails", "flag_bad_phones",
                  "standardise_casing", "normalise_dates"],
  "date_columns": ["date_of_birth"]
}
```

`validate_emails` / `flag_bad_phones` don't delete rows — they add a
`<column>_valid` boolean column so the business can review flagged rows
themselves rather than silently losing data. Returns `.csv` with
`X-Rows-Before` / `X-Rows-After` headers.

## 8. Email Signature Generator
`POST /email-signature/generate` — JSON body, returns raw HTML (`text/html`)
ready to paste into Gmail/Outlook signature settings.

```json
{
  "name": "Jane Dlamini",
  "job_title": "Operations Manager",
  "company": "Acme Traders",
  "email": "jane@acme.co.za",
  "phone": "+27 82 123 4567",
  "website": "https://acme.co.za",
  "logo_url": "https://acme.co.za/logo.png",
  "accent_color": "#1a1a2e"
}
```

---

## Errors

All endpoints return standard FastAPI error shapes:
```json
{ "detail": "human-readable message" }
```
- `400` — bad/invalid input, wrong file type, content doesn't match extension
- `413` — file too big for that endpoint
- `429` — rate limit hit
- `500` / `504` — processing failure / timeout

## Rate limits (per IP, in-process)

| Tier | Default | Endpoints |
|---|---|---|
| Standard | 20/hour | qr, image compress/convert, file compress, csv clean |
| Heavy | 10/hour | background-remove, pdf-to-images, csv-to-xlsx, docx-to-pdf |

Configurable via `SYNKRA_RATE_LIMIT` / `SYNKRA_RATE_LIMIT_HEAVY` env vars.
**Known limitation:** limits are enforced per-process, in memory. Fine for
one instance; if this gets load-balanced across multiple containers, swap
`app/core/ratelimit.py` to slowapi's Redis backend or limits will be
effectively multiplied by instance count.

## File size limits (env-configurable)
- General upload: 25MB (`SYNKRA_MAX_UPLOAD_MB`)
- Images: 15MB (`SYNKRA_MAX_IMAGE_MB`)
- CSV: 10MB (`SYNKRA_MAX_CSV_MB`)

## Security model (Section 29 of the product spec)
Every upload is validated on **actual file content**, not the filename or
declared Content-Type: `python-magic` sniffs the real magic bytes and the
request is rejected if they don't match an allowlisted type, or if the
extension contradicts the sniffed content. Blocked outright: `.exe .dll
.bat .cmd .scr .sh .ps1 .msi .jar .vbs .js .py .php .zip .rar .7z`.
Nothing is ever written to a shared/persistent path — each job gets a
UUID-named temp directory that's deleted right after the response streams.

## DOCX → PDF — why it's off by default
High-fidelity DOCX→PDF conversion genuinely needs a real document engine
— LibreOffice headless (`soffice`) is the standard open-source route. That
binary is 300MB+, which conflicts directly with "keep this lightweight,
don't eat server space." Two honest options, your call:
1. Leave it disabled (current default) and don't advertise DOCX→PDF at launch.
2. Run it as a **separate** small container/worker with LibreOffice
   installed, set `SYNKRA_ENABLE_DOCX_TO_PDF=true` only on that worker, and
   route just that one endpoint to it. Don't bloat the main image for it.

I did not build a lightweight fallback (e.g. python-docx + reportlab)
because it can't reproduce real DOCX formatting/layout — it would silently
produce wrong-looking output, which is worse than not shipping the feature.

## Deploying
```bash
cd backend
docker build -t synkra-utilities-api .
docker run -p 8000:8000 --env-file .env synkra-utilities-api
```
Interactive API docs (Swagger UI) are auto-served at `/docs` — useful for
the frontend team to poke at requests/responses directly while wiring up
the UI, and worth disabling (`docs_url=None` in `main.py`) once it's live
in production if you don't want it public.

## What was deliberately NOT built here
Per the spec's "no dashboard" list, this repo covers exactly the
account-free, storage-free tools. Link shortener, contact page, inquiry
form, and chat widget all need accounts + a dashboard + persistent storage
— those are a separate, later build with real authentication and a
database, not an extension of this stateless API.
