"""
Conformance tests for the principal-track state machine.

The same scenarios are covered by the TypeScript reference at
`@telaro/ars-solana` (`tests/state.test.ts`). An implementation that
passes both should produce identical `Job` states given identical
event logs. That equivalence is SPEC.md section 5.
"""

import pytest

from telaro_ars import (
    ARSTransitionError,
    Closed,
    Disputed,
    EvidenceSubmitted,
    JobOpened,
    PrincipalReleased,
    UnderwritingDecided,
    UnderwritingStarted,
    apply_event,
    is_terminal,
    replay,
)


def _open():
    return JobOpened(
        job_id="job-1",
        at=1,
        agent="AgentPubkey",
        requestor="DAppPubkey",
        exposure_atomic=1_000_000_000,
    )


def test_open_creates_await_underwriting():
    job = apply_event(None, _open())
    assert job.state == "AWAIT_UNDERWRITING"
    assert job.released_atomic == 0
    assert job.job_id == "job-1"


def test_underwriting_decided_pass_to_releasable():
    j0 = apply_event(None, _open())
    j1 = apply_event(j0, UnderwritingStarted(job_id="job-1", at=2))
    j2 = apply_event(
        j1, UnderwritingDecided(job_id="job-1", at=3, passed=True)
    )
    assert j2.state == "RELEASABLE"


def test_underwriting_decided_fail_to_rejected_is_terminal():
    j0 = apply_event(None, _open())
    j1 = apply_event(j0, UnderwritingStarted(job_id="job-1", at=2))
    j2 = apply_event(
        j1,
        UnderwritingDecided(
            job_id="job-1", at=3, passed=False, failure_code="BOND_BELOW_MIN"
        ),
    )
    assert j2.state == "REJECTED"
    assert is_terminal(j2.state)


def test_principal_can_be_drawn_more_than_once():
    log = [
        _open(),
        UnderwritingStarted(job_id="job-1", at=2),
        UnderwritingDecided(job_id="job-1", at=3, passed=True),
        PrincipalReleased(job_id="job-1", at=4, amount_atomic=500_000_000),
        PrincipalReleased(job_id="job-1", at=5, amount_atomic=500_000_000),
    ]
    job = replay(log)
    assert job.state == "EXECUTING"
    assert job.released_atomic == 1_000_000_000


def test_happy_path_to_closed_no_dispute():
    log = [
        _open(),
        UnderwritingStarted(job_id="job-1", at=2),
        UnderwritingDecided(job_id="job-1", at=3, passed=True),
        PrincipalReleased(job_id="job-1", at=4, amount_atomic=1_000_000_000),
        EvidenceSubmitted(
            job_id="job-1", at=5, action_hash="0xabc", outcome="success"
        ),
        Closed(job_id="job-1", at=6, resolution="no_dispute"),
    ]
    job = replay(log)
    assert job.state == "CLOSED"
    assert is_terminal(job.state)


def test_dispute_path_to_closed():
    log = [
        _open(),
        UnderwritingStarted(job_id="job-1", at=2),
        UnderwritingDecided(job_id="job-1", at=3, passed=True),
        PrincipalReleased(job_id="job-1", at=4, amount_atomic=1_000_000_000),
        EvidenceSubmitted(
            job_id="job-1", at=5, action_hash="0xabc", outcome="failed"
        ),
        Disputed(job_id="job-1", at=6, claim="ClaimPubkey"),
        Closed(job_id="job-1", at=7, resolution="dispute_upheld"),
    ]
    job = replay(log)
    assert job.state == "CLOSED"


def test_illegal_transition_principal_before_underwriting():
    j0 = apply_event(None, _open())
    with pytest.raises(ARSTransitionError):
        apply_event(j0, PrincipalReleased(job_id="job-1", at=2, amount_atomic=1))


def test_illegal_transition_event_for_terminal_job():
    log = [
        _open(),
        UnderwritingStarted(job_id="job-1", at=2),
        UnderwritingDecided(
            job_id="job-1", at=3, passed=False, failure_code="X"
        ),
    ]
    job = replay(log)
    with pytest.raises(ARSTransitionError, match="terminal"):
        apply_event(job, UnderwritingStarted(job_id="job-1", at=4))


def test_event_for_wrong_job_id():
    j0 = apply_event(None, _open())
    with pytest.raises(ARSTransitionError, match="does not match"):
        apply_event(j0, UnderwritingStarted(job_id="job-other", at=2))


def test_event_for_unknown_job():
    with pytest.raises(ARSTransitionError, match="unknown job"):
        apply_event(None, UnderwritingStarted(job_id="job-1", at=2))


def test_replay_empty_log_raises():
    with pytest.raises(ARSTransitionError, match="empty"):
        replay([])


def test_disputed_only_allowed_from_evidence_submitted():
    log = [
        _open(),
        UnderwritingStarted(job_id="job-1", at=2),
        UnderwritingDecided(job_id="job-1", at=3, passed=True),
        PrincipalReleased(job_id="job-1", at=4, amount_atomic=1),
    ]
    job = replay(log)
    with pytest.raises(ARSTransitionError):
        apply_event(job, Disputed(job_id="job-1", at=5, claim="C"))
