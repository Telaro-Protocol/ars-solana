"""
On-chain binding: ARS principal-track settlement to Telaro instructions.

Two surfaces here:

  1. `*_intent` functions return an `InstructionIntent`: a structured,
     readable description of what would be sent (program id, accounts,
     args). Useful for logging, dry-run, and as the source of truth for
     account ordering. Always available.

  2. `build_*_ix` functions return a `solders.instruction.Instruction`
     fully encoded and ready to assemble into a transaction. In v0.1
     only `build_view_bond_ix` is implemented; the other four return
     `NotImplementedError` and instead point the caller at the npm
     reference implementation. They are tracked for v0.2 in SPEC.md
     §10.

Why ship a partial chain-encoding surface in v0.1: the `view_bond`
gate-check call is by far the most-called instruction (every DApp
that gates capital does it), and re-implementing it in Python lets
the Python ARS user reach the chain without pulling in a Node
runtime. The other four are write-path admin instructions called by
the protocol operator, not by the typical ARS consumer, and are
better re-implemented once the Anchor IDL is stable rather than
hand-coded now.

PDA layout is in SPEC.md §3. Instruction discriminators follow
Anchor's `sha256("global:<name>")[:8]` rule.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey

from telaro_ars.constants import PROGRAM_ID_DEVNET


# -------------------------------------------------------------------- #
#  Discriminator: deterministic from the snake_case instruction name.   #
# -------------------------------------------------------------------- #


def _disc(name: str) -> bytes:
    """Anchor instruction discriminator: sha256('global:<name>')[:8]."""
    return hashlib.sha256(f"global:{name}".encode("utf-8")).digest()[:8]


# -------------------------------------------------------------------- #
#  Pure params (mirror src/binding.ts).                                 #
# -------------------------------------------------------------------- #


@dataclass(frozen=True)
class LockCollateralParams:
    """Pass into `lock_collateral_intent` / `build_view_bond_ix`."""

    job_id: str
    agent: Pubkey
    min_bond_atomic: int
    """USDC atomic (6dp). The minimum bond the agent must hold."""
    min_score: int
    """0-1000."""


@dataclass(frozen=True)
class SlashCollateralParams:
    job_id: str
    claim: Pubkey
    """The `Claim` PDA being resolved."""
    agent: Pubkey
    bond_mint: Pubkey
    claimer_bond_ata: Pubkey
    """The harmed party's bond-mint ATA; receives the slashed funds."""
    signer: Pubkey
    """The agent's controller, signing the accept."""


@dataclass(frozen=True)
class UnlockCollateralParams:
    job_id: str
    agent: Pubkey
    bond_mint: Pubkey
    controller: Pubkey
    controller_bond_ata: Pubkey
    amount_atomic: int


@dataclass(frozen=True)
class PayPremiumParams:
    job_id: str
    payer: Pubkey
    underwriter: Pubkey
    """`UnderwriterPool` vault PDA, or the `InsuranceVault` backstop."""
    amount_atomic: int


@dataclass(frozen=True)
class ReleasePrincipalParams:
    job_id: str
    agent: Pubkey
    credit_line: Pubkey
    """`CreditLine` PDA: ['credit-line', agent]."""
    amount_atomic: int


# -------------------------------------------------------------------- #
#  Instruction intents (always available).                              #
# -------------------------------------------------------------------- #


@dataclass(frozen=True)
class InstructionIntent:
    """
    A structured description of an instruction without on-chain
    encoding. Useful for dry-run, logging, and tests. The caller
    converts to a real `solders.instruction.Instruction` either via
    `build_*_ix` (where implemented) or via a v0.2 encoder.
    """

    method: str
    """Anchor instruction name (snake_case)."""
    program_id: Pubkey
    accounts: list[tuple[str, Pubkey, bool, bool]] = field(default_factory=list)
    """(role, pubkey, is_signer, is_writable) tuples in account order."""
    args: dict = field(default_factory=dict)


def lock_collateral_intent(
    params: LockCollateralParams,
    program_id: Pubkey = PROGRAM_ID_DEVNET,
) -> InstructionIntent:
    """Maps `SettlementLayer.lock_collateral` onto Telaro `view_bond`."""
    return InstructionIntent(
        method="view_bond",
        program_id=program_id,
        accounts=[("agent", params.agent, False, False)],
        args={
            "min_bond": params.min_bond_atomic,
            "min_score": params.min_score,
        },
    )


def slash_collateral_intent(
    params: SlashCollateralParams,
    program_id: Pubkey = PROGRAM_ID_DEVNET,
) -> InstructionIntent:
    """Maps `slash_collateral` onto Telaro `resolve_claim` (accept)."""
    return InstructionIntent(
        method="resolve_claim",
        program_id=program_id,
        accounts=[
            ("claim", params.claim, False, True),
            ("agent", params.agent, False, True),
            ("bond_mint", params.bond_mint, False, False),
            ("claimer_bond_ata", params.claimer_bond_ata, False, True),
            ("signer", params.signer, True, True),
        ],
        args={"action": 0},  # 0 = builder accepts the claim
    )


def unlock_collateral_intent(
    params: UnlockCollateralParams,
    program_id: Pubkey = PROGRAM_ID_DEVNET,
) -> InstructionIntent:
    """Maps `unlock_collateral` onto Telaro `withdraw_bond`."""
    return InstructionIntent(
        method="withdraw_bond",
        program_id=program_id,
        accounts=[
            ("agent", params.agent, False, True),
            ("bond_mint", params.bond_mint, False, False),
            ("controller", params.controller, True, True),
            ("controller_bond_ata", params.controller_bond_ata, False, True),
        ],
        args={"amount": params.amount_atomic},
    )


def pay_premium_intent(
    params: PayPremiumParams,
    program_id: Pubkey = PROGRAM_ID_DEVNET,
) -> InstructionIntent:
    """Maps `pay_premium` onto `process_pool_yield` or `fund_insurance`."""
    # The choice between the two is the implementation's; v0.1 reports
    # the call as `process_pool_yield` (decentralised path) by default.
    # See SPEC.md §2.4.
    return InstructionIntent(
        method="process_pool_yield",
        program_id=program_id,
        accounts=[
            ("payer", params.payer, True, True),
            ("underwriter", params.underwriter, False, True),
        ],
        args={"amount": params.amount_atomic},
    )


def release_principal_intent(
    params: ReleasePrincipalParams,
    program_id: Pubkey = PROGRAM_ID_DEVNET,
) -> InstructionIntent:
    """Maps `release_principal` onto Telaro `request_credit`."""
    return InstructionIntent(
        method="request_credit",
        program_id=program_id,
        accounts=[
            ("agent", params.agent, False, True),
            ("credit_line", params.credit_line, False, True),
        ],
        args={"amount": params.amount_atomic},
    )


# -------------------------------------------------------------------- #
#  Encoded instructions (v0.1: view_bond only).                         #
# -------------------------------------------------------------------- #


def build_view_bond_ix(
    params: LockCollateralParams,
    program_id: Pubkey = PROGRAM_ID_DEVNET,
) -> Instruction:
    """
    Build the `view_bond` instruction, encoded.

    The data layout matches `buildViewBondIx` in the TypeScript SDK
    (`sdk/src/instructions.ts`):
      offset  0..8   = sha256('global:view_bond')[:8]
      offset  8..16  = min_bond as u64 little-endian
      offset 16..18  = min_score as u16 little-endian

    Accounts (1):
      0: agent PDA, not signer, not writable
    """
    if not (0 <= params.min_score <= 0xFFFF):
        raise ValueError("min_score must fit in u16 (0..65535)")
    if not (0 <= params.min_bond_atomic <= 0xFFFFFFFFFFFFFFFF):
        raise ValueError("min_bond_atomic must fit in u64")
    data = (
        _disc("view_bond")
        + params.min_bond_atomic.to_bytes(8, "little")
        + params.min_score.to_bytes(2, "little")
    )
    return Instruction(
        program_id=program_id,
        accounts=[AccountMeta(pubkey=params.agent, is_signer=False, is_writable=False)],
        data=data,
    )


# Stubs for the other four. They raise NotImplementedError with a
# pointer to the npm reference so a caller doesn't silently send a
# malformed instruction.

def _not_implemented_yet(method: str) -> None:
    raise NotImplementedError(
        f"build_{method}_ix is reserved for v0.2 of telaro-ars. "
        f"For v0.1, use the npm @telaro/ars-solana reference or call "
        f"the chain via your own Anchor IDL client. The instruction "
        f"intent (account ordering and args) is available via "
        f"{method}_intent()."
    )


def build_resolve_claim_ix(*_args, **_kwargs) -> Instruction:
    _not_implemented_yet("slash_collateral")
    raise AssertionError  # unreachable


def build_withdraw_bond_ix(*_args, **_kwargs) -> Instruction:
    _not_implemented_yet("unlock_collateral")
    raise AssertionError  # unreachable


def build_process_pool_yield_ix(*_args, **_kwargs) -> Instruction:
    _not_implemented_yet("pay_premium")
    raise AssertionError  # unreachable


def build_request_credit_ix(*_args, **_kwargs) -> Instruction:
    _not_implemented_yet("release_principal")
    raise AssertionError  # unreachable
