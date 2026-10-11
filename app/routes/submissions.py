from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.errors import ErrorEnvelope
from app.models import SubmissionStatus
from app.processing import SubmissionProcessor, get_processor
from app.services.submissions import submit

router = APIRouter(prefix="/submissions", tags=["submissions"])


class AnswerIn(BaseModel):
    item_key: str = Field(min_length=1, max_length=100)
    passed: bool


class SubmissionIn(BaseModel):
    site_id: int
    device_id: str = Field(min_length=1, max_length=100)
    template_version: int
    captured_at: AwareDatetime
    # Caps the work a hostile request can cause; rejected before any database access.
    answers: list[AnswerIn] = Field(max_length=200)


class SubmissionOut(BaseModel):
    id: int
    status: SubmissionStatus


@router.post(
    "",
    response_model=SubmissionOut,
    status_code=201,
    responses={400: {"model": ErrorEnvelope}},
)
async def create_submission(
    body: SubmissionIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    processor: Annotated[SubmissionProcessor, Depends(get_processor)],
) -> SubmissionOut:
    submission = await submit(
        session,
        processor,
        site_id=body.site_id,
        device_id=body.device_id,
        template_version=body.template_version,
        captured_at=body.captured_at,
        answers=[(a.item_key, a.passed) for a in body.answers],
    )
    return SubmissionOut(id=submission.id, status=submission.status)
