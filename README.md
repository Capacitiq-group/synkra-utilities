# Synkra Business Utilities

Free, no-account, no-dashboard business utilities. Acquisition/SEO layer for
Synkra — see `docs/API.md` for the full endpoint reference and the product
spec that drove these decisions.

## What's here (Phase 1 — no account, no dashboard, no storage)
- QR Code Generator
- Image Compressor
- Image Converter
- File Compressor (PDF, DOCX)
- File Converter (PDF→images, CSV→XLSX; DOCX→PDF disabled by default, see docs)
- Background Remover (self-hosted, rembg)
- CSV Cleaner
- Email Signature Generator

Not in this repo yet: link shortener, contact page, inquiry form, chat
widget — those need accounts/dashboard/DB per the spec and are a separate
build.

## Structure
```
backend/
  app/
    main.py            # FastAPI app, wires all routers
    config.py           # env-driven settings, limits, feature flags
    core/
      security.py       # upload validation (magic bytes, not just extension)
      cleanup.py        # temp-dir lifecycle
      ratelimit.py       # per-IP rate limiting
    routers/             # one file per utility
  requirements.txt
  Dockerfile
docs/
  API.md                 # endpoint reference for the frontend team
```

## Quickstart (local)
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
# → http://localhost:8000/docs
```

## Deploy
```bash
cd backend
docker build -t synkra-utilities-api .
docker run -p 8000:8000 synkra-utilities-api
```

## Pushing this to GitHub
This was built in a sandbox with no outbound network access, so I couldn't
push directly to `Capacitiq-group/synkra-utilities`. From your machine (or
Claude Code, which does have network):

```bash
# unzip the delivered archive, then from inside synkra-utilities/
git init   # if not already
git add .
git commit -m "Phase 1: stateless business utilities API"
git branch -M main
git remote add origin https://github.com/Capacitiq-group/synkra-utilities.git
git push -u origin main
```

**Revoke the PAT you pasted in chat now** — it was shared in plaintext,
so even though it was fine-grained and scoped to this one repo, treat it
as burned regardless of whether it ever got used.

## Before this goes live
- Set `CORS_ORIGINS` to your actual site domain(s).
- Decide on DOCX→PDF (see `docs/API.md`) — leave disabled unless you're
  running a separate LibreOffice worker for it.
- The rate limiter is in-memory/per-process — fine for one instance, needs
  a Redis backend if you scale horizontally.
- `/docs` (Swagger UI) is public by default — turn it off in prod if you
  don't want the API surface browsable.
