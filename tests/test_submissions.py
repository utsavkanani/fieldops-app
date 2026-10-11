from sqlmodel import func, select, text

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


def publish_version(run_db, site_id: int, version: int) -> None:
    """Make `version` the site's current template; earlier versions become superseded."""

    async def publish(session):
        old = await session.exec(select(ChecklistTemplate).where(ChecklistTemplate.site_id == site_id))
        for template in old:
            template.is_current = False
            session.add(template)
        template = ChecklistTemplate(site_id=site_id, version=version, is_current=True)
        session.add(template)
        await session.flush()
        session.add_all(TemplateItem(template_id=template.id, key=key) for key in ITEM_KEYS)
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
