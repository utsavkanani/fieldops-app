"""Receiving checklist submissions: validate against the template, store, process.

No FastAPI here. The route turns HTTP into these arguments and the result back into
a response; this module only knows about the database and the processor.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.errors import SubmissionRejected
from app.models import ChecklistTemplate, Site, Submission, SubmissionAnswer, TemplateItem
from app.processing import SubmissionProcessor


async def submit(
    session: AsyncSession,
    processor: SubmissionProcessor,
    *,
    site_id: int,
    device_id: str,
    template_version: int,
    captured_at: datetime,
    answers: Sequence[tuple[str, bool]],
) -> Submission:
    """Store a submission and process it. Raises SubmissionRejected if it's invalid."""
    if await session.get(Site, site_id) is None:
        raise SubmissionRejected(f"unknown site {site_id}")

    template = await _find_template(session, site_id, template_version)
    await _check_answers(session, template, [key for key, _ in answers])

    submission = Submission(
        site_id=site_id,
        template_id=template.id,
        device_id=device_id,
        captured_at=captured_at.astimezone(UTC).replace(tzinfo=None),
        # A superseded version is kept, not rejected: the manager already walked the site.
        needs_review=not template.is_current,
    )
    session.add(submission)
    await session.flush()
    session.add_all(
        SubmissionAnswer(submission_id=submission.id, item_key=key, passed=passed)
        for key, passed in answers
    )
    # Committed as not_processed first, so a failure during processing leaves a row a retry can pick up.
    await session.commit()

    await processor.process(session, submission)
    return submission


async def _find_template(session: AsyncSession, site_id: int, version: int) -> ChecklistTemplate:
    template = (
        await session.exec(
            select(ChecklistTemplate).where(
                ChecklistTemplate.site_id == site_id,
                ChecklistTemplate.version == version,
            )
        )
    ).first()
    if template is None:
        raise SubmissionRejected(f"site {site_id} has no template v{version}")
    return template


async def _check_answers(session: AsyncSession, template: ChecklistTemplate, submitted: list[str]) -> None:
    """Every item on the template answered exactly once: the version answered, not the current one."""
    expected = set(
        (await session.exec(select(TemplateItem.key).where(TemplateItem.template_id == template.id))).all()
    )
    if len(submitted) != len(set(submitted)) or set(submitted) != expected:
        repeated = sorted({k for k in submitted if submitted.count(k) > 1})
        raise SubmissionRejected(
            f"answers don't match site {template.site_id} template v{template.version}: "
            f"missing={sorted(expected - set(submitted))} extra={sorted(set(submitted) - expected)} "
            f"repeated={repeated}"
        )
