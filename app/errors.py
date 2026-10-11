import logging

from fastapi import FastAPI, Request
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
    return JSONResponse(status_code=400, content=REJECTED.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(SubmissionRejected, _submission_rejected)
