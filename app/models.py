from datetime import datetime
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects.mysql import DATETIME
from sqlmodel import Field, SQLModel


class Site(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)


class ChecklistTemplate(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("site_id", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id")
    version: int


class TemplateItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    template_id: int = Field(foreign_key="checklisttemplate.id")
    key: str = Field(max_length=100)


class SubmissionStatus(StrEnum):
    NOT_PROCESSED = "not_processed"
    PROCESSED = "processed"


class Submission(SQLModel, table=True):
    # The idempotency key: a retried request from the same phone carries the same pair.
    __table_args__ = (UniqueConstraint("device_id", "captured_at"),)

    id: int | None = Field(default=None, primary_key=True)
    site_id: int = Field(foreign_key="site.id")
    template_id: int = Field(foreign_key="checklisttemplate.id")
    device_id: str = Field(max_length=100)
    # UTC, microsecond precision; plain MySQL DATETIME would drop the fraction.
    captured_at: datetime = Field(sa_type=DATETIME(fsp=6))
    status: SubmissionStatus = SubmissionStatus.NOT_PROCESSED


class SubmissionAnswer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    submission_id: int = Field(foreign_key="submission.id")
    item_key: str = Field(max_length=100)
    passed: bool
