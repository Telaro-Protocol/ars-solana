"""
ARS-Solana Profile v0.1 conformance harness.

Lets another implementation (TypeScript, Rust, future Python, future
non-Telaro implementations on Solana) verify against the same
behavioural corpus this reference uses. A conformant implementation
must:

  1. Reach the same `Job` state given the same event log (state
     machine equivalence).
  2. Reject the same illegal transitions with an error.
  3. Encode `view_bond` to byte-equivalent output for the same inputs.

The harness exposes:

  - `STATE_VECTORS`: a list of event logs paired with the expected
    terminal `Job` state. Implementations replay each and check.
  - `ILLEGAL_VECTORS`: event sequences that must raise the
    implementation's transition error.
  - `view_bond_vectors`: `(min_bond, min_score, expected_data_hex)`
    triples that exercise the byte-encoded instruction layout.
  - `run_self_test()`: runs the full suite against the reference
    Python implementation and returns a `ConformanceReport`.

A non-Python implementer reads the constants and ports them to their
language. We pin the expected outputs deterministically; if a future
profile version changes the layout, the version bump is the contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from solders.pubkey import Pubkey

from telaro_ars.binding import LockCollateralParams, build_view_bond_ix
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
from telaro_ars.state import ARSTransitionError, replay


_AGENT = Pubkey.from_string("4Nd1mYJgC7DsB3v9pkM9CRZxoUTfXn1kbm1zFM5hZRgM")


def _h(b: bytes) -> str:
    return b.hex()


# -------------------------------------------------------------------- #
#  Vector 1: state machine.                                             #
# -------------------------------------------------------------------- #


@dataclass(frozen=True)
class StateVector:
    """A complete log and the terminal state it must replay to."""

    name: str
    log: list[ArsEvent]
    expected_state: str
    expected_released_atomic: int = 0


STATE_VECTORS: list[StateVector] = [
    StateVector(
        name="awaiting underwriting after open",
        log=[
            JobOpened(
                job_id="j1", at=1, agent="A", requestor="D", exposure_atomic=10**9
            ),
        ],
        expected_state="AWAIT_UNDERWRITING",
    ),
    StateVector(
        name="rejected after failing underwriting",
        log=[
            JobOpened(
                job_id="j1", at=1, agent="A", requestor="D", exposure_atomic=10**9
            ),
            UnderwritingStarted(job_id="j1", at=2),
            UnderwritingDecided(
                job_id="j1", at=3, passed=False, failure_code="BOND_BELOW_MIN"
            ),
        ],
        expected_state="REJECTED",
    ),
    StateVector(
        name="executing after one principal draw",
        log=[
            JobOpened(
                job_id="j1", at=1, agent="A", requestor="D", exposure_atomic=10**9
            ),
            UnderwritingStarted(job_id="j1", at=2),
            UnderwritingDecided(job_id="j1", at=3, passed=True),
            PrincipalReleased(job_id="j1", at=4, amount_atomic=500_000_000),
        ],
        expected_state="EXECUTING",
        expected_released_atomic=500_000_000,
    ),
    StateVector(
        name="closed (no dispute)",
        log=[
            JobOpened(
                job_id="j1", at=1, agent="A", requestor="D", exposure_atomic=10**9
            ),
            UnderwritingStarted(job_id="j1", at=2),
            UnderwritingDecided(job_id="j1", at=3, passed=True),
            PrincipalReleased(job_id="j1", at=4, amount_atomic=10**9),
            EvidenceSubmitted(
                job_id="j1", at=5, action_hash="0xabc", outcome="success"
            ),
            Closed(job_id="j1", at=6, resolution="no_dispute"),
        ],
        expected_state="CLOSED",
        expected_released_atomic=10**9,
    ),
    StateVector(
        name="closed via dispute upheld",
        log=[
            JobOpened(
                job_id="j1", at=1, agent="A", requestor="D", exposure_atomic=10**9
            ),
            UnderwritingStarted(job_id="j1", at=2),
            UnderwritingDecided(job_id="j1", at=3, passed=True),
            PrincipalReleased(job_id="j1", at=4, amount_atomic=10**9),
            EvidenceSubmitted(
                job_id="j1", at=5, action_hash="0xabc", outcome="failed"
            ),
            Disputed(job_id="j1", at=6, claim="C"),
            Closed(job_id="j1", at=7, resolution="dispute_upheld"),
        ],
        expected_state="CLOSED",
        expected_released_atomic=10**9,
    ),
]


# -------------------------------------------------------------------- #
#  Vector 2: illegal transitions.                                        #
# -------------------------------------------------------------------- #


@dataclass(frozen=True)
class IllegalVector:
    """A log that must raise the implementation's transition error."""

    name: str
    log: list[ArsEvent]


ILLEGAL_VECTORS: list[IllegalVector] = [
    IllegalVector(
        name="principal before underwriting",
        log=[
            JobOpened(
                job_id="j1", at=1, agent="A", requestor="D", exposure_atomic=1
            ),
            PrincipalReleased(job_id="j1", at=2, amount_atomic=1),
        ],
    ),
    IllegalVector(
        name="event for unknown job",
        log=[UnderwritingStarted(job_id="ghost", at=1)],
    ),
    IllegalVector(
        name="event after terminal CLOSED",
        log=[
            JobOpened(
                job_id="j1", at=1, agent="A", requestor="D", exposure_atomic=1
            ),
            UnderwritingStarted(job_id="j1", at=2),
            UnderwritingDecided(
                job_id="j1", at=3, passed=False, failure_code="X"
            ),
            UnderwritingStarted(job_id="j1", at=4),
        ],
    ),
]


# -------------------------------------------------------------------- #
#  Vector 3: view_bond byte encoding.                                    #
# -------------------------------------------------------------------- #


@dataclass(frozen=True)
class ViewBondVector:
    """An (input, expected canonical byte form) pair for view_bond."""

    name: str
    min_bond_atomic: int
    min_score: int
    expected_data_hex: str
    """Hex of the 18-byte instruction data (8 disc + 8 u64 LE + 2 u16 LE)."""


def _view_bond_expected(min_bond: int, min_score: int) -> str:
    disc = hashlib.sha256(b"global:view_bond").digest()[:8]
    return _h(
        disc
        + min_bond.to_bytes(8, "little")
        + min_score.to_bytes(2, "little")
    )


VIEW_BOND_VECTORS: list[ViewBondVector] = [
    ViewBondVector(
        name="zeros",
        min_bond_atomic=0,
        min_score=0,
        expected_data_hex=_view_bond_expected(0, 0),
    ),
    ViewBondVector(
        name="1 USDC, score 700",
        min_bond_atomic=1_000_000,
        min_score=700,
        expected_data_hex=_view_bond_expected(1_000_000, 700),
    ),
    ViewBondVector(
        name="1000 USDC, score 800",
        min_bond_atomic=1_000_000_000,
        min_score=800,
        expected_data_hex=_view_bond_expected(1_000_000_000, 800),
    ),
    ViewBondVector(
        name="u64-max bond, u16-max score",
        min_bond_atomic=0xFFFFFFFFFFFFFFFF,
        min_score=0xFFFF,
        expected_data_hex=_view_bond_expected(
            0xFFFFFFFFFFFFFFFF, 0xFFFF
        ),
    ),
]


# -------------------------------------------------------------------- #
#  Self-test runner.                                                    #
# -------------------------------------------------------------------- #


@dataclass
class ConformanceReport:
    """Result of running the suite against an implementation."""

    state_passed: int = 0
    state_failed: list[str] = field(default_factory=list)
    illegal_passed: int = 0
    illegal_failed: list[str] = field(default_factory=list)
    view_bond_passed: int = 0
    view_bond_failed: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.state_failed or self.illegal_failed or self.view_bond_failed)

    def summary(self) -> str:
        lines = [
            f"State vectors:       {self.state_passed}/{self.state_passed + len(self.state_failed)}",
            f"Illegal vectors:     {self.illegal_passed}/{self.illegal_passed + len(self.illegal_failed)}",
            f"view_bond vectors:   {self.view_bond_passed}/{self.view_bond_passed + len(self.view_bond_failed)}",
        ]
        for f in self.state_failed:
            lines.append(f"  STATE FAIL: {f}")
        for f in self.illegal_failed:
            lines.append(f"  ILLEGAL FAIL: {f}")
        for f in self.view_bond_failed:
            lines.append(f"  VIEW_BOND FAIL: {f}")
        return "\n".join(lines)


def run_self_test() -> ConformanceReport:
    """Run the full conformance corpus against this reference
    implementation. Returns a `ConformanceReport`; `report.ok` is True
    when every vector passed."""
    r = ConformanceReport()

    for v in STATE_VECTORS:
        try:
            job = replay(v.log)
            ok = (
                job.state == v.expected_state
                and job.released_atomic == v.expected_released_atomic
            )
            if ok:
                r.state_passed += 1
            else:
                r.state_failed.append(
                    f"{v.name}: got state={job.state} released={job.released_atomic}"
                )
        except Exception as e:
            r.state_failed.append(f"{v.name}: raised {type(e).__name__}: {e}")

    for v in ILLEGAL_VECTORS:
        try:
            replay(v.log)
            r.illegal_failed.append(f"{v.name}: should have raised")
        except ARSTransitionError:
            r.illegal_passed += 1
        except Exception as e:
            r.illegal_failed.append(
                f"{v.name}: raised wrong type {type(e).__name__}"
            )

    for v in VIEW_BOND_VECTORS:
        ix = build_view_bond_ix(
            LockCollateralParams(
                job_id="conformance",
                agent=_AGENT,
                min_bond_atomic=v.min_bond_atomic,
                min_score=v.min_score,
            )
        )
        got = _h(bytes(ix.data))
        if got == v.expected_data_hex:
            r.view_bond_passed += 1
        else:
            r.view_bond_failed.append(
                f"{v.name}: expected {v.expected_data_hex}, got {got}"
            )

    return r


def as_json() -> dict[str, Any]:
    """Dump the suite as JSON so non-Python implementations can read it
    without parsing this module."""
    return {
        "profile": "ARS-Solana Profile v0.1",
        "state_vectors": [
            {
                "name": v.name,
                "expected_state": v.expected_state,
                "expected_released_atomic": v.expected_released_atomic,
                "log": [e.__dict__ for e in v.log],
            }
            for v in STATE_VECTORS
        ],
        "illegal_vectors": [
            {"name": v.name, "log": [e.__dict__ for e in v.log]}
            for v in ILLEGAL_VECTORS
        ],
        "view_bond_vectors": [
            {
                "name": v.name,
                "min_bond_atomic": v.min_bond_atomic,
                "min_score": v.min_score,
                "expected_data_hex": v.expected_data_hex,
            }
            for v in VIEW_BOND_VECTORS
        ],
    }


if __name__ == "__main__":  # pragma: no cover
    report = run_self_test()
    print(report.summary())
    print()
    print("Result:", "PASS" if report.ok else "FAIL")
