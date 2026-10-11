from sqlmodel import select

from app.models import ChecklistTemplate, Site, Submission, SubmissionAnswer, TemplateItem

ITEM_KEYS = ["fire_exit_clear", "first_aid_stocked"]


def seed_site(run_db) -> int:
    async def seed(session):
        site = Site(name="Depot 1")
        session.add(site)
        await session.flush()
        template = ChecklistTemplate(site_id=site.id, version=1)
        session.add(template)
        await session.flush()
        session.add_all(TemplateItem(template_id=template.id, key=key) for key in ITEM_KEYS)
        await session.commit()
        return site.id

    return run_db(seed)


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
        return submission, answers

    submission, answers = run_db(stored)
    assert submission.id == body["id"]
    assert submission.status == "processed"
    assert sorted(a.item_key for a in answers) == ITEM_KEYS
