"""
ARS principal-track events for the Telaro Solana implementation.

These mirror `src/events.ts` from `@telaro/ars-solana` byte for byte
(same fields, same names, same semantics). A Python consumer that
holds an event log produced by either side can replay it through
`state.replay`.

Job lifecycle is event-sourced: a `Job` carries no mutable state of
its own. The current state is derived by folding this log through
`apply_event` (state.py). Event-sourced design matches the ARS
reference and makes the principal-track lifecycle auditable.

Scope: principal track only. Fee track is deferred to v0.2 per
SPEC.md sections 1 and 10.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


@dataclass(frozen=True)
class JobOpened:
    """A capital-handling job is opened by a DApp delegating to an agent."""

    job_id: str
    at: int
    agent: str
    requestor: str
    exposure_atomic: int
    type: Literal["JobOpened"] = "JobOpened"


@dataclass(frozen=True)
class UnderwritingStarted:
    """Underwriting review has begun (the Telaro `view_bond` evaluation)."""

    job_id: str
    at: int
    type: Literal["UnderwritingStarted"] = "UnderwritingStarted"


@dataclass(frozen=True)
class UnderwritingDecided:
    """The underwriting verdict from `view_bond`."""

    job_id: str
    at: int
    passed: bool
    failure_code: str | None = None
    type: Literal["UnderwritingDecided"] = "UnderwritingDecided"


@dataclass(frozen=True)
class PrincipalReleased:
    """Principal was released to the agent (a `request_credit` draw)."""

    job_id: str
    at: int
    amount_atomic: int
    type: Literal["PrincipalReleased"] = "PrincipalReleased"


@dataclass(frozen=True)
class EvidenceSubmitted:
    """The agent's execution result was recorded (Telaro `record_action`)."""

    job_id: str
    at: int
    action_hash: str
    outcome: Literal["success", "failed"]
    type: Literal["EvidenceSubmitted"] = "EvidenceSubmitted"


@dataclass(frozen=True)
class Disputed:
    """A claim was filed against the job. Hands off to the Telaro claim flow."""

    job_id: str
    at: int
    claim: str
    type: Literal["Disputed"] = "Disputed"


@dataclass(frozen=True)
class Closed:
    """The job reached a terminal outcome."""

    job_id: str
    at: int
    resolution: Literal["no_dispute", "dispute_upheld", "dispute_rejected"]
    type: Literal["Closed"] = "Closed"


ArsEvent = Union[
    JobOpened,
    UnderwritingStarted,
    UnderwritingDecided,
    PrincipalReleased,
    EvidenceSubmitted,
    Disputed,
    Closed,
]
