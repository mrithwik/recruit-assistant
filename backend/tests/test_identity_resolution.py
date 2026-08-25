from app.models.schemas import CandidateProfile
from app.scanning.identity_resolution import compute_fingerprint, merge_into_candidate


def test_fingerprint_prefers_email():
    profile = CandidateProfile(email="A@Example.com", legal_first_name="Jordan", legal_last_name="Rivera")
    assert compute_fingerprint(profile) == "email:a@example.com"


def test_fingerprint_falls_back_to_name_phone():
    profile = CandidateProfile(legal_first_name="Jordan", legal_last_name="Rivera", phone="(555) 123-4567")
    fp = compute_fingerprint(profile)
    assert fp == "name:jordanrivera:phone:5551234567"


def test_merge_new_candidate_created_when_none_existing():
    profile = CandidateProfile(email="a@example.com", legal_first_name="Jordan", skills=["python"])
    candidate = merge_into_candidate(None, profile, "email:a@example.com")
    assert candidate.legal_first_name == "Jordan"
    assert candidate.skills == ["python"]


def test_merge_updates_without_erasing_known_fields():
    profile = CandidateProfile(email="a@example.com", legal_first_name="Jordan", skills=["python"])
    existing = merge_into_candidate(None, profile, "email:a@example.com")

    # A second resume for the same person adds a skill but has no phone —
    # existing.phone (still blank here) should stay blank, not error; new
    # skill should merge in without dropping the old one.
    second_pass_profile = CandidateProfile(email="a@example.com", skills=["fastapi"])
    updated = merge_into_candidate(existing, second_pass_profile, "email:a@example.com")

    assert set(updated.skills) == {"python", "fastapi"}
    assert updated.legal_first_name == "Jordan"  # not erased by the blank field on pass two
