"""
Report route handlers — Sub-Task 5.

Endpoints
─────────
    GET /api/report/{job_id}      — poll job status or retrieve the full ReportPayload JSON
    GET /api/report/{job_id}/pdf  — stream the generated PDF as a file download

Behaviour summary
─────────────────
    ``GET /api/report/{job_id}``
        - 404  if ``job_id`` is unknown
        - Returns ``JobStatusResponse``  while status is "pending" | "running" | "error"
        - Returns ``ReportPayload``      once status is "complete"

    ``GET /api/report/{job_id}/pdf``
        - 404  if ``job_id`` is unknown
        - 404  if job is not yet complete or has no PDF on disk
        - 200  ``FileResponse`` (application/pdf, Content-Disposition: attachment)
"""

from __future__ import annotations

import os
from pathlib import Path as FSPath
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi import status as http_status
from fastapi.responses import FileResponse

from app.api.dependencies import get_db, get_job_store
from app.core.job_store import JobStore
from app.logger import get_logger
from app.portfolio import crud
from app.schemas.report import JobStatusResponse, ReportPayload
from sqlalchemy.orm import Session

logger = get_logger(__name__)

router = APIRouter()


# ── GET /api/report/{job_id} ──────────────────────────────────────────────────


@router.get(
    "/report/{job_id}",
    summary="Get job status or completed report",
    description=(
        "While the job is running, returns a lightweight ``JobStatusResponse`` "
        "with the current pipeline step. "
        "Once the job is complete, returns the full ``ReportPayload`` JSON. "
        "Returns 404 for unknown job IDs."
    ),
    # response_model intentionally omitted: the return type varies between
    # JobStatusResponse and ReportPayload.  FastAPI will serialise whichever
    # Pydantic model the handler returns.
)
async def get_report(
    job_id: UUID = Path(..., description="UUID of the analysis job to retrieve"),
    store: JobStore = Depends(get_job_store),
    db: Session = Depends(get_db),
) -> JobStatusResponse | ReportPayload:
    """
    Retrieve the current state of an analysis job.

    - ``"pending"`` / ``"running"`` / ``"error"`` → ``JobStatusResponse``
    - ``"complete"`` → ``ReportPayload`` (full analysis result)
    - Unknown ``job_id`` in memory but found in DB cache → ``ReportPayload``
    - Unknown ``job_id`` → HTTP 404
    """
    job_id_str = str(job_id)
    job = store.get_job(job_id_str)

    if job is None:
        # The in-memory JobStore was cleared (server restart).
        # Fall back to the persistent report cache in the database.
        cached = crud.get_report_cache(db, job_id_str)
        if cached is not None:
            logger.debug(
                "Serving report from DB cache (job not in memory)",
                extra={"job_id": job_id},
            )
            return ReportPayload.model_validate_json(cached.payload_json)

        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id_str}' not found.",
        )

    if job.status == "complete":
        result = job.result
        # result is stored as a plain dict by the orchestrator; coerce to model.
        if isinstance(result, dict):
            return ReportPayload(**result)
        # Already a ReportPayload instance (e.g. in tests).
        return result  # type: ignore[return-value]

    # Job is still in progress or has errored — return the lightweight response.
    return JobStatusResponse(
        status=job.status,
        current_step=job.current_step,
        error=job.error,
    )


# ── GET /api/report/{job_id}/pdf ──────────────────────────────────────────────


@router.get(
    "/report/{job_id}/pdf",
    summary="Download the generated PDF report",
    description=(
        "Stream the PDF report as an attachment download. "
        "Returns 404 when the job is unknown, not yet complete, or the PDF "
        "file has not been generated / has already been cleaned up."
    ),
    response_class=FileResponse,
)
async def get_report_pdf(
    job_id: UUID = Path(..., description="UUID of the analysis job whose PDF to download"),
    store: JobStore = Depends(get_job_store),
    db: Session = Depends(get_db),
) -> FileResponse:
    """
    Serve the PDF for a completed analysis job.

    - Unknown ``job_id`` → HTTP 404
    - Job not ``"complete"`` → HTTP 404 with a descriptive message
    - ``pdf_path`` is ``None`` or file no longer on disk → HTTP 404
    - Otherwise → ``FileResponse`` (``application/pdf``, attachment)
    """
    job_id_str = str(job_id)
    job = store.get_job(job_id_str)
    pdf_path: str | None = None

    if job is None:
        # Fall back to the persistent DB cache (server may have restarted).
        cached = crud.get_report_cache(db, job_id_str)
        if cached is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Job '{job_id_str}' not found.",
            )
        cached_payload = ReportPayload.model_validate_json(cached.payload_json)
        pdf_path = cached_payload.pdf_path
    else:
        if job.status != "complete":
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=(
                    f"PDF is not available: job '{job_id_str}' has status '{job.status}'. "
                    "Wait until the job is complete before downloading the PDF."
                ),
            )

        # Retrieve pdf_path from the stored result.
        result = job.result
        if isinstance(result, dict):
            pdf_path = result.get("pdf_path")
        elif hasattr(result, "pdf_path"):
            pdf_path = result.pdf_path

    if not pdf_path:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"PDF has not been generated for job '{job_id_str}' yet.",
        )

    # ── Path-traversal guard ──────────────────────────────────────────────────
    # pdf_path comes from DB-stored data; verify it resolves inside the
    # configured output directory before serving the file.
    from app.config import settings as _settings  # local import avoids circularity

    resolved = FSPath(pdf_path).resolve()
    allowed_dir = FSPath(_settings.pdf_output_dir).resolve()
    if not str(resolved).startswith(str(allowed_dir) + os.sep) and resolved != allowed_dir:
        logger.warning(
            "PDF path outside allowed directory — refusing to serve",
            extra={"job_id": job_id, "pdf_path": pdf_path, "resolved": str(resolved)},
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="PDF file is no longer available (it may have been cleaned up).",
        )

    if not os.path.isfile(pdf_path):
        logger.warning(
            "PDF file missing from disk",
            extra={"job_id": job_id, "pdf_path": pdf_path},
        )
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="PDF file is no longer available (it may have been cleaned up).",
        )

    # Derive a clean filename for the Content-Disposition header.
    filename = os.path.basename(pdf_path)
    
    logger.info(
        "Serving PDF download",
        extra={"job_id": job_id, "file_name": filename},
    )
    
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
    )
