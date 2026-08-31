"""Regression test for a real bug hit during manual testing: the frontend's
date-range picker sends toISOString() (a "Z"-suffixed, timezone-aware
string), while every date_submitted elsewhere in the codebase is naive UTC
(datetime.utcnow()) — comparing the two raised "can't compare offset-naive
and offset-aware datetimes" and silently failed a real scan job (see
project-log). ScanFolderRequest/ScanEmailRequest now normalize incoming
dates to naive UTC at the request boundary."""

from datetime import datetime

from app.models.schemas import ScanEmailRequest, ScanFolderRequest


def test_aware_iso_date_is_normalized_to_naive_utc():
    req = ScanEmailRequest(account_ids=["acct-1"], date_start="2026-08-01T00:00:00.000Z", date_end="2026-08-20T00:00:00.000Z")
    assert req.date_start.tzinfo is None
    assert req.date_end.tzinfo is None
    assert req.date_start == datetime(2026, 8, 1)
    assert req.date_end == datetime(2026, 8, 20)


def test_aware_non_utc_offset_is_converted_before_stripping_tzinfo():
    # +05:00 offset — must convert to UTC first, not just strip the offset.
    req = ScanFolderRequest(folder_paths=["/tmp"], date_start="2026-08-01T05:00:00+05:00")
    assert req.date_start.tzinfo is None
    assert req.date_start == datetime(2026, 8, 1, 0, 0, 0)


def test_naive_date_passes_through_unchanged():
    req = ScanEmailRequest(account_ids=["acct-1"], date_start="2026-08-01T00:00:00")
    assert req.date_start == datetime(2026, 8, 1)


def test_none_dates_stay_none():
    req = ScanEmailRequest(account_ids=["acct-1"])
    assert req.date_start is None
    assert req.date_end is None


def test_naive_and_aware_dates_are_now_comparable():
    """The actual failure mode: comparing the normalized request date against
    a naive date_submitted must not raise."""
    req = ScanEmailRequest(account_ids=["acct-1"], date_start="2026-08-01T00:00:00.000Z")
    naive_submitted = datetime.utcnow()
    assert (naive_submitted < req.date_start) in (True, False)  # doesn't raise
