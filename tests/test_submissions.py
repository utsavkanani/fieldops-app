import pytest
from sqlmodel import func, select, text

from app.db import get_session
from app.main import app
from app.models import ChecklistTemplate, Site, Submission, SubmissionAnswer, TemplateItem

ITEM_KEYS = ["fire_exit_clear", "first_aid_stocked"]
REJECTED = {"error": {"code": "invalid_submission", "message": "Submission rejected"}}


def seed_site(run_db) -> int:
    async def seed(session):
        site = Site(name="Depot 1")
        session.add(site)
        await session.flush()
        template = ChecklistTemplate(site_id=site.id, version=1, is_current=True)
        session.add(template)
        await session.flush()
        session.add_all(TemplateItem(template_id=template.id, key=key) for key in ITEM_KEYS)
        await session.commit()
        return site.id

    return run_db(seed)


def publish_version(run_db, site_id: int, version: int, keys: list[str] = ITEM_KEYS) -> None:
    """Make `version` the site's current template; earlier versions become superseded."""

    async def publish(session):
        old = await session.exec(select(ChecklistTemplate).where(ChecklistTemplate.site_id == site_id))
        for template in old:
            template.is_current = False
            session.add(template)
        template = ChecklistTemplate(site_id=site_id, version=version, is_current=True)
        session.add(template)
        await session.flush()
        session.add_all(TemplateItem(template_id=template.id, key=key) for key in keys)
        await session.commit()

    run_db(publish)


def payload(site_id: int, **overrides) -> dict:
    body = {
        "site_id": site_id,
        "device_id": "phone-1",
        "template_version": 1,
        "captured_at": "2026-10-10T08:00:00.123456Z",
        "answers": [{"item_key": key, "passed": True} for key in ITEM_KEYS],
    }
    return body | overrides


def test_valid_submission_is_stored_and_processed(client, run_db):
    site_id = seed_site(run_db)

    response = client.post("/submissions", json=payload(site_id))

    assert response.status_code == 201
    body = response.json()
    assert body == {"id": body["id"], "status": "processed"}

    async def stored(session):
        submission = (await session.exec(select(Submission))).one()
        answers = (await session.exec(select(SubmissionAnswer))).all()
        raw_status = (await session.exec(text("SELECT status FROM submission"))).scalar_one()
        return submission, answers, raw_status

    submission, answers, raw_status = run_db(stored)
    assert submission.id == body["id"]
    assert submission.status == "processed"
    # The table stores the same value the API returns.
    assert raw_status == "processed"
    assert submission.needs_review is False
    assert sorted(a.item_key for a in answers) == ITEM_KEYS


def count_submissions(run_db) -> int:
    async def count(session):
        return (await session.exec(select(func.count()).select_from(Submission))).one()

    return run_db(count)


def test_unknown_site_is_rejected_without_detail(client, run_db):
    seed_site(run_db)

    response = client.post("/submissions", json=payload(site_id=999_999))

    assert response.status_code == 400
    assert response.json() == REJECTED
    assert count_submissions(run_db) == 0


def test_superseded_version_is_accepted_and_flagged_for_review(client, run_db):
    site_id = seed_site(run_db)
    publish_version(run_db, site_id, version=2)

    # The manager's phone still has v1.
    response = client.post("/submissions", json=payload(site_id, template_version=1))

    assert response.status_code == 201
    assert response.json()["status"] == "processed"

    async def stored(session):
        submission = (await session.exec(select(Submission))).one()
        template = await session.get(ChecklistTemplate, submission.template_id)
        return submission, template

    submission, template = run_db(stored)
    assert template.version == 1
    assert submission.needs_review is True


def test_version_that_never_existed_is_rejected(client, run_db):
    site_id = seed_site(run_db)

    response = client.post("/submissions", json=payload(site_id, template_version=99))

    assert response.status_code == 400
    assert response.json() == REJECTED
    assert count_submissions(run_db) == 0


def answers(*keys: str) -> list[dict]:
    return [{"item_key": key, "passed": True} for key in keys]


@pytest.mark.parametrize(
    "bad_answers",
    [
        pytest.param(answers("fire_exit_clear"), id="missing-item"),
        pytest.param(answers(*ITEM_KEYS, "not_on_template"), id="extra-item"),
        pytest.param(answers(*ITEM_KEYS, "fire_exit_clear"), id="repeated-item"),
    ],
)
def test_answers_must_match_the_template_exactly(client, run_db, bad_answers):
    site_id = seed_site(run_db)

    response = client.post("/submissions", json=payload(site_id, answers=bad_answers))

    assert response.status_code == 400
    assert response.json() == REJECTED
    assert count_submissions(run_db) == 0


def test_answers_are_checked_against_the_version_answered(client, run_db):
    site_id = seed_site(run_db)
    publish_version(run_db, site_id, version=2, keys=[*ITEM_KEYS, "ladder_secured"])

    # v1 answered with v2's items: wrong for the version it claims.
    v2_items_as_v1 = payload(site_id, template_version=1, answers=answers(*ITEM_KEYS, "ladder_secured"))
    assert client.post("/submissions", json=v2_items_as_v1).status_code == 400

    # v1 answered with v1's items: fine, even though v2 is current.
    v1_items = payload(site_id, template_version=1, captured_at="2026-10-10T09:00:00Z")
    assert client.post("/submissions", json=v1_items).status_code == 201


def test_oversized_answer_list_is_rejected_before_touching_the_database(client):
    class NoDatabase:
        def __getattr__(self, name):
            raise AssertionError(f"database used: session.{name}")

    async def no_database():
        yield NoDatabase()

    app.dependency_overrides[get_session] = no_database
    flood = answers(*(f"item_{i}" for i in range(201)))

    response = client.post("/submissions", json=payload(site_id=1, answers=flood))

    assert response.status_code == 400
    assert response.json() == REJECTED


def count_answers(run_db) -> int:
    async def count(session):
        return (await session.exec(select(func.count()).select_from(SubmissionAnswer))).one()

    return run_db(count)


def test_retry_of_processed_submission_returns_it_unchanged(client, run_db):
    site_id = seed_site(run_db)

    first = client.post("/submissions", json=payload(site_id))
    retry = client.post("/submissions", json=payload(site_id))

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert count_submissions(run_db) == 1
    assert count_answers(run_db) == len(ITEM_KEYS)
