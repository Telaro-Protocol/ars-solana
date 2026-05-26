"""
telaro-ars: Python adapter for the ARS-Solana Profile.

The ARS abstract layer (t54-labs/AgenticRiskStandard) is Python.
This package implements its `SettlementLayer` and `CollateralVault`
abstract base classes against the Telaro Anchor program on Solana.

The same profile (PDA layout, event schemas, conformance criteria) is
specified in:
  https://github.com/Telaro-Protocol/ars-solana/blob/main/SPEC.md

The TypeScript reference implementation is `@telaro/ars-solana` on
npm and is the source of truth for the runtime mapping. The Python
package here mirrors that surface for Python ARS consumers.
"""

from telaro_ars.abc import (
    SettlementLayer,
    CollateralVault,
    DepositInfo,
    DepositStatus,
)
from telaro_ars.events import (
    ArsEvent,
    JobOpened,
    UnderwritingStarted,
    UnderwritingDecided,
    PrincipalReleased,
    EvidenceSubmitted,
    Disputed,
    Closed,
)
from telaro_ars.state import (
    Job,
    PrincipalState,
    ARSTransitionError,
    apply_event,
    replay,
    is_terminal,
)
from telaro_ars.settlement import (
    TelaroSettlement,
    TELARO_SETTLEMENT_MAP,
    SettlementBinding,
)
from telaro_ars.binding import (
    LockCollateralParams,
    SlashCollateralParams,
    UnlockCollateralParams,
    PayPremiumParams,
    ReleasePrincipalParams,
    InstructionIntent,
    lock_collateral_intent,
    slash_collateral_intent,
    unlock_collateral_intent,
    pay_premium_intent,
    release_principal_intent,
    build_view_bond_ix,
    build_resolve_claim_ix,
    build_withdraw_bond_ix,
    build_process_pool_yield_ix,
    build_request_credit_ix,
)
from telaro_ars.constants import (
    PROGRAM_ID_DEVNET,
    MIN_BOND_USDC_ATOMIC,
    MIN_SCORE_FOR_CREDIT,
    MAX_LEVERAGE_RATIO,
)

__version__ = "0.4.0"

__all__ = [
    "__version__",
    # ABCs
    "SettlementLayer",
    "CollateralVault",
    "DepositInfo",
    "DepositStatus",
    # events
    "ArsEvent",
    "JobOpened",
    "UnderwritingStarted",
    "UnderwritingDecided",
    "PrincipalReleased",
    "EvidenceSubmitted",
    "Disputed",
    "Closed",
    # state
    "Job",
    "PrincipalState",
    "ARSTransitionError",
    "apply_event",
    "replay",
    "is_terminal",
    # settlement
    "TelaroSettlement",
    "TELARO_SETTLEMENT_MAP",
    "SettlementBinding",
    # binding
    "LockCollateralParams",
    "SlashCollateralParams",
    "UnlockCollateralParams",
    "PayPremiumParams",
    "ReleasePrincipalParams",
    "InstructionIntent",
    "lock_collateral_intent",
    "slash_collateral_intent",
    "unlock_collateral_intent",
    "pay_premium_intent",
    "release_principal_intent",
    "build_view_bond_ix",
    "build_resolve_claim_ix",
    "build_withdraw_bond_ix",
    "build_process_pool_yield_ix",
    "build_request_credit_ix",
    # constants
    "PROGRAM_ID_DEVNET",
    "MIN_BOND_USDC_ATOMIC",
    "MIN_SCORE_FOR_CREDIT",
    "MAX_LEVERAGE_RATIO",
]
