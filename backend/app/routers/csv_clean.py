"""
CSV Cleaner — Section 16. Basic processing only, no account, no storage.
Operations are opt-in via the `operations` field so the caller controls
exactly what happens to their data.
"""
import io
import re
from enum import Enum

import pandas as pd
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import ALLOWED_CSV_MIME, MAX_CSV_BYTES, RATE_LIMIT_DEFAULT
from app.core.ratelimit import limiter
from app.core.security import read_and_validate_upload

router = APIRouter(prefix="/csv/clean", tags=["CSV Cleaner"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+\d][\d\s\-()]{6,}$")


class Operation(str, Enum):
    remove_duplicates = "remove_duplicates"
    trim_whitespace = "trim_whitespace"
    standardise_headers = "standardise_headers"
    remove_blank_rows = "remove_blank_rows"
    validate_emails = "validate_emails"          # flags invalid emails, doesn't delete rows
    flag_bad_phones = "flag_bad_phones"           # flags malformed numbers
    standardise_casing = "standardise_casing"     # Title Case on text columns
    normalise_dates = "normalise_dates"           # best-effort -> YYYY-MM-DD


class CleanOptions(BaseModel):
    operations: list[Operation] = [
        Operation.trim_whitespace,
        Operation.remove_blank_rows,
        Operation.remove_duplicates,
    ]
    date_columns: list[str] = []


def _clean(df: pd.DataFrame, opts: CleanOptions) -> pd.DataFrame:
    ops = set(opts.operations)

    if Operation.standardise_headers in ops:
        df.columns = [
            re.sub(r"\s+", "_", str(c).strip().lower()) for c in df.columns
        ]

    if Operation.trim_whitespace in ops:
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": pd.NA})

    if Operation.remove_blank_rows in ops:
        df = df.dropna(how="all")

    if Operation.remove_duplicates in ops:
        df = df.drop_duplicates()

    if Operation.standardise_casing in ops:
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype(str).str.title().replace({"Nan": pd.NA})

    if Operation.validate_emails in ops:
        email_cols = [c for c in df.columns if "email" in c.lower()]
        for col in email_cols:
            df[f"{col}_valid"] = df[col].astype(str).apply(lambda v: bool(_EMAIL_RE.match(v)))

    if Operation.flag_bad_phones in ops:
        phone_cols = [c for c in df.columns if "phone" in c.lower() or "tel" in c.lower()]
        for col in phone_cols:
            df[f"{col}_valid"] = df[col].astype(str).apply(lambda v: bool(_PHONE_RE.match(v)))

    if Operation.normalise_dates in ops:
        target_cols = opts.date_columns or [c for c in df.columns if "date" in c.lower()]
        for col in target_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True).dt.strftime("%Y-%m-%d")

    return df


@router.post("")
@limiter.limit(RATE_LIMIT_DEFAULT)
async def clean_csv(request: Request, file: UploadFile, options: CleanOptions = CleanOptions()):
    data = await read_and_validate_upload(file, ALLOWED_CSV_MIME, MAX_CSV_BYTES)
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(400, f"Could not parse CSV: {exc}") from exc

    rows_before = len(df)
    df = _clean(df, options)
    rows_after = len(df)

    out = io.StringIO()
    df.to_csv(out, index=False)
    out_bytes = io.BytesIO(out.getvalue().encode("utf-8"))

    return StreamingResponse(
        out_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="cleaned.csv"',
            "X-Rows-Before": str(rows_before),
            "X-Rows-After": str(rows_after),
            "Access-Control-Expose-Headers": "X-Rows-Before,X-Rows-After",
        },
    )
