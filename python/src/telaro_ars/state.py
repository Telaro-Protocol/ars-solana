"""
ARS principal-track state machine.

`replay` folds an event log (events.py) into a `Job`. `apply_event`
is the single transition function; an illegal transition raises
`ARSTransitionError`.

This file mirrors `src/state.ts` from `@telaro/ars-solana` exactly.
A reference implementation that replays the same event log through
either side should produce an identical `Job`. That equivalence is
what SPEC.md §5 calls a conformance test.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Literal

from telaro_ars.events import (
    ArsEvent,
    Closed,
    Disputed,
    EvidenceSubmitted,
    JobOpened,
    PrincipalReleased,
    UnderwritingDecided,
    UnderwritingStarted,
)

PrincipalState = Literal[
    "AWAIT_UNDERWRITING",
    "UNDERWRITING",
    "REJECTED",
    "RELEASABLE",
    "EXECUTING",
    "EVIDENCE_SUBMITTED",
    "DISPUTED",
    "CLOSED",
]

_TERMINAL: frozenset[PrincipalState] = frozenset(("REJECTED", "CLOSED"))


def is_terminal(state: PrincipalState) -> bool:
    """A job in a terminal state accepts no further events."""
    return state in _TERMINAL


@dataclass(frozen=True)
class Job:
    """A job's full derived state."""

    job_id: str
    agent: str
    requestor: str
    exposure_atomic: int
    state: PrincipalState
    released_atomic: int
    last_event_at: int


class ARSTransitionError(Exception):
    """Raised by `apply_event` for any illegal transition."""


def apply_event(job: Job | None, event: ArsEvent) -> Job:
    """
    Apply one event to a job, returning the next job. Pass `None` as
    `job` only for the opening `JobOpened` event. Raises
    `ARSTransitionError` for any illegal transition.
    """
    if isinstance(event, JobOpened):
        if job is not None:
            raise ARSTransitionError(
                f"JobOpened for {event.job_id}: job already exists"
            )
        return Job(
            job_id=event.job_id,
            agent=event.agent,
            requestor=event.requestor,
            exposure_atomic=event.exposure_atomic,
            state="AWAIT_UNDERWRITING",
            released_atomic=0,
            last_event_at=event.at,
        )

    if job is None:
        raise ARSTransitionError(
            f"{event.type} for unknown job {event.job_id}"
        )
    if job.job_id != event.job_id:
        raise ARSTransitionError(
            f"event job_id {event.job_id} does not match job {job.job_id}"
        )
    if is_terminal(job.state):
        raise ARSTransitionError(
            f"{event.type}: job {job.job_id} is terminal ({job.state})"
        )

    def _to(state: PrincipalState, **patch) -> Job:
        return replace(job, state=state, last_event_at=event.at, **patch)

    def _illegal() -> None:
        raise ARSTransitionError(
            f"{event.type} is not allowed in state {job.state}"
        )

    if isinstance(event, UnderwritingStarted):
        if job.state != "AWAIT_UNDERWRITING":
            _illegal()
        return _to("UNDERWRITING")

    if isinstance(event, UnderwritingDecided):
        if job.state != "UNDERWRITING":
            _illegal()
        return _to("RELEASABLE" if event.passed else "REJECTED")

    if isinstance(event, PrincipalReleased):
        # Principal can be drawn more than once: the credit line supports
        # repeated `request_credit` calls, so EXECUTING accepts it too.
        if job.state not in ("RELEASABLE", "EXECUTING"):
            _illegal()
        return _to(
            "EXECUTING",
            released_atomic=job.released_atomic + event.amount_atomic,
        )

    if isinstance(event, EvidenceSubmitted):
        if job.state != "EXECUTING":
            _illegal()
        return _to("EVIDENCE_SUBMITTED")

    if isinstance(event, Disputed):
        if job.state != "EVIDENCE_SUBMITTED":
            _illegal()
        return _to("DISPUTED")

    if isinstance(event, Closed):
        if job.state not in ("EVIDENCE_SUBMITTED", "DISPUTED"):
            _illegal()
        return _to("CLOSED")

    raise ARSTransitionError(f"unknown event type: {type(event).__name__}")


def replay(events: Iterable[ArsEvent]) -> Job:
    """Derive the current job by replaying its full event log."""
    job: Job | None = None
    for event in events:
        job = apply_event(job, event)
    if job is None:
        raise ARSTransitionError("cannot replay an empty event log")
    return job
