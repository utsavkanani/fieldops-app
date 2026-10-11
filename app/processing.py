from typing import Protocol

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Submission, SubmissionStatus


class SubmissionProcessor(Protocol):
    async def process(self, session: AsyncSession, submission: Submission) -> None: ...


class InlineProcessor:
    """Processes in the request. A queue-backed processor would replace this."""

    async def process(self, session: AsyncSession, submission: Submission) -> None:
        # The real work (alerting on failed checks, reporting) goes here.
        submission.status = SubmissionStatus.PROCESSED
        session.add(submission)
        await session.commit()


def get_processor() -> SubmissionProcessor:
    return InlineProcessor()
