from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.config import API_PREFIX, APP_NAME, CORS_ORIGINS
from app.core.ratelimit import limiter
from app.routers import (
    background_remove,
    csv_clean,
    email_signature,
    file_compress,
    file_convert,
    image_compress,
    image_convert,
    invoice,
    purchase_order,
    qr,
    quotation,
    receipt,
)

app = FastAPI(
    title=APP_NAME,
    description=(
        "Stateless processing endpoints for Synkra's free business utilities. "
        "No accounts, no persistent storage — files are processed in memory/temp "
        "and discarded immediately after the response is sent."
    ),
    version="1.0.0",
)

app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Please try again later."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(qr.router, prefix=API_PREFIX)
app.include_router(image_compress.router, prefix=API_PREFIX)
app.include_router(image_convert.router, prefix=API_PREFIX)
app.include_router(file_compress.router, prefix=API_PREFIX)
app.include_router(file_convert.router, prefix=API_PREFIX)
app.include_router(background_remove.router, prefix=API_PREFIX)
app.include_router(csv_clean.router, prefix=API_PREFIX)
app.include_router(email_signature.router, prefix=API_PREFIX)
app.include_router(invoice.router, prefix=API_PREFIX)
app.include_router(quotation.router, prefix=API_PREFIX)
app.include_router(purchase_order.router, prefix=API_PREFIX)
app.include_router(receipt.router, prefix=API_PREFIX)


@app.get("/health")
def health():
    return {"status": "ok"}
