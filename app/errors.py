import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    """The one error shape every failure returns."""

    error: ErrorDetail


class SubmissionRejected(Exception):
    """An invalid submission. The reason is logged server-side and never sent to the client."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


REJECTED = ErrorEnvelope(error=ErrorDetail(code="invalid_submission", message="Submission rejected"))


async def _submission_rejected(request: Request, exc: SubmissionRejected) -> JSONResponse:
    logger.warning("Submission rejected: %s", exc.reason)
    return JSONResponse(status_code=400, content=REJECTED.model_dump(mode="json"))


async def _request_invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Location and error type only; the input values could be huge or hostile.
    reasons = [f"{'.'.join(map(str, e['loc']))}: {e['type']}" for e in exc.errors()[:5]]
    return await _submission_rejected(request, SubmissionRejected(f"invalid request {reasons}"))


INTERNAL = ErrorEnvelope(error=ErrorDetail(code="internal_error", message="Internal error"))


async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content=INTERNAL.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SubmissionRejected, _submission_rejected)
    # Anything unexpected: same envelope, a 500 the phone will retry, details only in the log.
    app.add_exception_handler(Exception, _unexpected)
    # FastAPI's default is a 422 with field-level detail; this keeps one envelope, no detail.
    app.add_exception_handler(RequestValidationError, _request_invalid)
