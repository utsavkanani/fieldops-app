from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db import get_session
from app.errors import ErrorEnvelope, SubmissionRejected
from app.models import (
    ChecklistTemplate,
    Site,
    Submission,
    SubmissionAnswer,
    SubmissionStatus,
    TemplateItem,
)
from app.processing import SubmissionProcessor, get_processor

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
    if await session.get(Site, body.site_id) is None:
        raise SubmissionRejected(f"unknown site {body.site_id}")

    template = (
        await session.exec(
            select(ChecklistTemplate).where(
                ChecklistTemplate.site_id == body.site_id,
                ChecklistTemplate.version == body.template_version,
            )
        )
    ).first()
    if template is None:
        raise SubmissionRejected(f"site {body.site_id} has no template v{body.template_version}")

    # Checked against the version the manager answered, not the current one.
    expected = set(
        (await session.exec(select(TemplateItem.key).where(TemplateItem.template_id == template.id))).all()
    )
    submitted = [a.item_key for a in body.answers]
    if len(submitted) != len(set(submitted)) or set(submitted) != expected:
        repeated = sorted({k for k in submitted if submitted.count(k) > 1})
        raise SubmissionRejected(
            f"answers don't match site {body.site_id} template v{body.template_version}: "
            f"missing={sorted(expected - set(submitted))} extra={sorted(set(submitted) - expected)} "
            f"repeated={repeated}"
        )

    submission = Submission(
        site_id=body.site_id,
        template_id=template.id,
        device_id=body.device_id,
        captured_at=body.captured_at.astimezone(UTC).replace(tzinfo=None),
        # A superseded version is kept, not rejected: the manager already walked the site.
        needs_review=not template.is_current,
    )
    session.add(submission)
    await session.flush()
    session.add_all(
        SubmissionAnswer(submission_id=submission.id, item_key=a.item_key, passed=a.passed)
        for a in body.answers
    )
    # Committed as not_processed first, so a failure during processing leaves a row a retry can pick up.
    await session.commit()

    await processor.process(session, submission)
    return SubmissionOut(id=submission.id, status=submission.status)
