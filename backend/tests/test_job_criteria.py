import uuid

from app.criteria.builtin import BUILTIN_CRITERIA
from app.criteria.service import get_job_criteria, seed_builtin_criteria, set_job_criterion
from app.models.db import Job


def test_get_job_criteria_returns_full_library_unselected_by_default(storage):
    with storage.session() as session:
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", raw_text="Python")
        session.add(job)
        session.commit()

        seed_builtin_criteria(session)
        pairs = get_job_criteria(session, job.id)

        assert len(pairs) == len(BUILTIN_CRITERIA)
        assert all(selection is None for _, selection in pairs)


def test_set_job_criterion_persists_value_and_bumps_criteria_version(storage):
    with storage.session() as session:
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", raw_text="Python")
        session.add(job)
        session.commit()
        job_id = job.id
        seed_builtin_criteria(session)

        criterion_id = get_job_criteria(session, job_id)[1][0].id  # "Minimum years of experience"
        set_job_criterion(session, job_id, criterion_id, enabled=True, value="5")

    with storage.session() as session:
        job = session.get(Job, job_id)
        assert job.criteria_version == 2  # bumped from 1

        pairs = get_job_criteria(session, job_id)
        matching = [(c, s) for c, s in pairs if c.id == criterion_id][0]
        assert matching[1].enabled is True
        assert matching[1].value == "5"


def test_set_job_criterion_twice_updates_in_place_not_duplicates(storage):
    with storage.session() as session:
        job = Job(id=str(uuid.uuid4()), title="Backend Engineer", raw_text="Python")
        session.add(job)
        session.commit()
        seed_builtin_criteria(session)
        criterion = get_job_criteria(session, job.id)[0][0]

        set_job_criterion(session, job.id, criterion.id, enabled=True, value="first")
        set_job_criterion(session, job.id, criterion.id, enabled=True, value="second")

        pairs = get_job_criteria(session, job.id)
        matches = [s for c, s in pairs if c.id == criterion.id and s is not None]
        assert len(matches) == 1
        assert matches[0].value == "second"
