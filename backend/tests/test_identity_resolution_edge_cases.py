from app.models.schemas import CandidateProfile
from app.scanning.identity_resolution import compute_fingerprint


def test_unidentifiable_resumes_get_distinct_fingerprints_not_one_shared_key():
    """Two different people who both submitted resumes with no extractable
    name, email, or phone (a thin/garbled resume) must NOT collide onto the
    same identity — that would silently merge unrelated candidates."""
    profile_a = CandidateProfile(raw_text="some garbled scan content A")
    profile_b = CandidateProfile(raw_text="some garbled scan content B")

    fp_a = compute_fingerprint(profile_a)
    fp_b = compute_fingerprint(profile_b)

    assert fp_a != fp_b
    assert fp_a.startswith("unidentified:")
