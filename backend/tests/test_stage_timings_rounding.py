"""QA regression, deterministic version: _merge_stage_timings must sum RAW
(unrounded) per-stage floats, and only _round_stage_timings — called once,
at final display — should quantize. Rounding before summing can silently
zero out real work: two calls each contributing 0.004s individually round
to 0.00 (each under the 0.005 threshold), and 0.00 + 0.00 stays 0.00 even
though the true total (0.008s) would correctly round to 0.01. This bypasses
real wall-clock timing entirely (which is inherently flaky for a workload
small enough to sit right at the rounding threshold — see the live
integration coverage in test_scan_stage_timings.py for that angle) and
proves the numeric behavior directly."""

import pytest

from app.routes.scan import _merge_stage_timings, _round_stage_timings


def test_merging_before_rounding_preserves_small_real_contributions():
    # Each call's real time individually rounds to 0.00 in isolation, but
    # summed raw first and rounded once at the end, the true total survives.
    call_a = {"parse": 0.004}
    call_b = {"parse": 0.004}

    merged = _merge_stage_timings(call_a, call_b)
    assert merged["parse"] == 0.008  # unrounded — nothing lost yet

    displayed = _round_stage_timings(merged)
    assert displayed["parse"] == 0.01  # rounds to a non-zero, correct total


def test_rounding_each_call_first_would_have_lost_the_same_contributions():
    # Documents the exact bug this guards against: if each call's dict were
    # rounded to 0.00 *before* merging (the old, broken order), summing
    # already-zeroed numbers can never recover the true total.
    already_rounded_a = {"parse": round(0.004, 2)}
    already_rounded_b = {"parse": round(0.004, 2)}
    assert already_rounded_a["parse"] == 0.0
    assert already_rounded_b["parse"] == 0.0

    wrongly_merged = _merge_stage_timings(already_rounded_a, already_rounded_b)
    assert wrongly_merged["parse"] == 0.0  # the bug: real work, reported as none


def test_merge_and_round_across_three_calls_with_missing_keys():
    merged = _merge_stage_timings(
        {"parse": 0.01, "embed": 0.0},
        {"parse": 0.003},
        {"summarize": 0.02},
    )
    assert merged["parse"] == pytest.approx(0.013)
    assert merged["embed"] == 0.0
    assert merged["summarize"] == pytest.approx(0.02)
    assert _round_stage_timings(merged) == {"parse": 0.01, "embed": 0.0, "summarize": 0.02}
