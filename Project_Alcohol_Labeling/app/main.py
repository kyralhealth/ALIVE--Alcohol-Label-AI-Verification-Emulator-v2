"""FastAPI app: single-label and batch verification endpoints + static UI."""
import asyncio
import csv
import io
import os
import time
from pathlib import Path
from typing import List, Optional

import anthropic
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .comparison import verify
from .demo import DemoExtractor
from .extraction import Extractor
from .schemas import (ApplicationData, BatchItemResult, BatchResponse,
                      VerificationResult)

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
BATCH_CONCURRENCY = 4  # parallel Claude calls per batch request
MAX_BATCH_FILES = 300  # "big importers dump 200-300 applications on us at once"

app = FastAPI(title="TTB Label Verifier", version="0.1.0")

DEMO_MODE = os.environ.get("LABEL_DEMO", "").strip() in ("1", "true", "yes")
extractor = DemoExtractor() if DEMO_MODE else Extractor()

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "mode": "demo" if DEMO_MODE else "live",
        "model": extractor.model,
        "api_key_configured": extractor.available,
    }


async def _verify_one(image_bytes: bytes, filename: str,
                      application: ApplicationData) -> VerificationResult:
    started = time.monotonic()
    try:
        extracted = await extractor.extract(image_bytes, filename=filename)
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=503, detail="Anthropic API key is invalid.")
    except anthropic.APIStatusError as exc:
        raise HTTPException(status_code=502,
                            detail="Label reading service error ({}).".format(exc.status_code))
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=502,
                            detail="Could not reach the label reading service — check network/firewall.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    result = verify(application, extracted)
    result.elapsed_seconds = round(time.monotonic() - started, 2)
    return result


def _read_upload(upload: UploadFile, data: bytes) -> bytes:
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413,
                            detail="Image too large (max 15 MB): {}".format(upload.filename))
    return data


@app.post("/api/verify", response_model=VerificationResult)
async def verify_single(
    image: UploadFile = File(...),
    brand_name: str = Form(""),
    class_type: str = Form(""),
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
) -> VerificationResult:
    data = _read_upload(image, await image.read())
    application = ApplicationData(
        brand_name=brand_name, class_type=class_type,
        alcohol_content=alcohol_content, net_contents=net_contents,
    )
    return await _verify_one(data, image.filename or "", application)


def _parse_applications_csv(raw: bytes) -> dict:
    """CSV columns: filename, brand_name, class_type, alcohol_content, net_contents."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Applications CSV must be UTF-8 encoded.")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "filename" not in [f.strip().lower() for f in reader.fieldnames]:
        raise HTTPException(
            status_code=400,
            detail="CSV must have a header row including a 'filename' column "
                   "(plus brand_name, class_type, alcohol_content, net_contents).")
    rows = {}
    for row in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        if row.get("filename"):
            rows[row["filename"]] = ApplicationData(
                brand_name=row.get("brand_name", ""),
                class_type=row.get("class_type", ""),
                alcohol_content=row.get("alcohol_content", ""),
                net_contents=row.get("net_contents", ""),
            )
    if not rows:
        raise HTTPException(status_code=400, detail="Applications CSV has no data rows.")
    return rows


@app.post("/api/verify-batch", response_model=BatchResponse)
async def verify_batch(
    images: List[UploadFile] = File(...),
    applications: UploadFile = File(...),
) -> BatchResponse:
    if len(images) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413,
                            detail="Batch limit is {} images per request.".format(MAX_BATCH_FILES))
    apps_by_filename = _parse_applications_csv(await applications.read())

    semaphore = asyncio.Semaphore(BATCH_CONCURRENCY)

    async def process(upload: UploadFile, data: bytes) -> BatchItemResult:
        name = upload.filename or "unnamed"
        application = apps_by_filename.get(name)
        if application is None:
            return BatchItemResult(
                filename=name,
                error="No row in the applications CSV with filename '{}'.".format(name))
        async with semaphore:
            try:
                result = await _verify_one(_read_upload(upload, data), name, application)
            except HTTPException as exc:
                return BatchItemResult(filename=name, application=application,
                                       error=str(exc.detail))
        return BatchItemResult(filename=name, application=application, result=result)

    payloads = [(u, await u.read()) for u in images]
    items = list(await asyncio.gather(*(process(u, d) for u, d in payloads)))

    matched = {i.filename for i in items}
    for filename in sorted(set(apps_by_filename) - matched):
        items.append(BatchItemResult(
            filename=filename, application=apps_by_filename[filename],
            error="Listed in the CSV but no image with this filename was uploaded."))

    counts = {"pass": 0, "review": 0, "fail": 0, "error": 0}
    for item in items:
        if item.error:
            counts["error"] += 1
        elif item.result:
            counts[item.result.overall] += 1
    return BatchResponse(items=items, summary=counts)


if __name__ == "__main__":
    # Lets `python -m app.main` work, honoring the PORT injected by hosts
    # like Replit, Render, and Railway.
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
