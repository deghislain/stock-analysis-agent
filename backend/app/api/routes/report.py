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

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from fastapi.responses import FileResponse

from app.api.dependencies import get_job_store
from app.core.job_store import JobStore
from app.logger import get_logger
from app.schemas.report import JobStatusResponse, ReportPayload

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
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> JobStatusResponse | ReportPayload:
    """
    Retrieve the current state of an analysis job.

    - ``"pending"`` / ``"running"`` / ``"error"`` → ``JobStatusResponse``
    - ``"complete"`` → ``ReportPayload`` (full analysis result)
    - Unknown ``job_id`` → HTTP 404
    """
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
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
    job_id: str,
    store: JobStore = Depends(get_job_store),
) -> FileResponse:
    """
    Serve the PDF for a completed analysis job.

    - Unknown ``job_id`` → HTTP 404
    - Job not ``"complete"`` → HTTP 404 with a descriptive message
    - ``pdf_path`` is ``None`` or file no longer on disk → HTTP 404
    - Otherwise → ``FileResponse`` (``application/pdf``, attachment)
    """
    job = store.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_id}' not found.",
        )

    if job.status != "complete":
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=(
                f"PDF is not available: job '{job_id}' has status '{job.status}'. "
                "Wait until the job is complete before downloading the PDF."
            ),
        )

    # Retrieve pdf_path from the stored result.
    result = job.result
    pdf_path: str | None = None

    if isinstance(result, dict):
        pdf_path = result.get("pdf_path")
    elif hasattr(result, "pdf_path"):
        pdf_path = result.pdf_path

    if not pdf_path:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"PDF has not been generated for job '{job_id}' yet.",
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
        extra={"job_id": job_id, "filename": filename},
    )

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
    )
