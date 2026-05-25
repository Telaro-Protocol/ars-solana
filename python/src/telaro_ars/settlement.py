"""
The ARS `SettlementLayer` realised against the Telaro Anchor program.

`TelaroSettlement` satisfies the abstract surface in abc.py by
producing `InstructionIntent` objects (and a real `view_bond`
instruction for `lock_collateral`). A caller composes those into a
transaction and signs/sends through their own `solana-py` or
`solders` async client.

`TELARO_SETTLEMENT_MAP` is the same authoritative mapping that lives
in the TypeScript reference at `src/settlement.ts`. The spec, the
runtime mapping, and this Python adapter all read from one source.
"""

from __future__ import annotations

from dataclasses import dataclass

from solders.pubkey import Pubkey

from telaro_ars.abc import SettlementLayer
from telaro_ars.binding import (
    InstructionIntent,
    LockCollateralParams,
    PayPremiumParams,
    ReleasePrincipalParams,
    SlashCollateralParams,
    UnlockCollateralParams,
    lock_collateral_intent,
    pay_premium_intent,
    release_principal_intent,
    slash_collateral_intent,
    unlock_collateral_intent,
)


@dataclass(frozen=True)
class SettlementBinding:
    """How an ARS `SettlementLayer` method is realised on the Telaro program."""

    instruction: str
    note: str


# The single source of truth on the Python side. Identical to
# `TELARO_SETTLEMENT_MAP` in `src/settlement.ts`.
TELARO_SETTLEMENT_MAP: dict[str, SettlementBinding] = {
    "lock_collateral": SettlementBinding(
        instruction="view_bond",
        note=(
            "standing bond + Agent.reserved_for_claims exposure accounting; "
            "leverage must stay <= MAX_LEVERAGE_RATIO (5x)"
        ),
    ),
    "slash_collateral": SettlementBinding(
        instruction="resolve_claim / arbiter_resolve",
        note="a ForUser ruling pays the harmed party out of the agent's bond",
    ),
    "unlock_collateral": SettlementBinding(
        instruction="withdraw_bond",
        note="released once the job closes, subject to the 30d withdrawal cooldown",
    ),
    "pay_premium": SettlementBinding(
        instruction="process_pool_yield / fund_insurance",
        note=(
            "premium routes to the UnderwriterPool (decentralised) "
            "or the InsuranceVault backstop"
        ),
    ),
    "release_principal": SettlementBinding(
        instruction="request_credit",
        note=(
            "under-collateralised draw from the UnderwriterPool; "
            "agent score must be >= 700"
        ),
    ),
    "lock_fee": SettlementBinding(
        instruction="(none)",
        note="fee track is out of scope for v0.1 (SPEC.md sections 1 and 10)",
    ),
    "release_fee": SettlementBinding(
        instruction="(none)",
        note="fee track is out of scope for v0.1 (SPEC.md sections 1 and 10)",
    ),
    "refund_fee": SettlementBinding(
        instruction="(none)",
        note="fee track is out of scope for v0.1 (SPEC.md sections 1 and 10)",
    ),
}


class TelaroSettlement(SettlementLayer):
    """
    The `SettlementLayer` ABC implemented against the Telaro Anchor
    program.

    The methods are `async` to match the upstream ABC, but the v0.1
    implementation returns `InstructionIntent` objects synchronously
    (no chain hit). A v0.2 implementation will wrap these with an
    Anchor IDL client to actually send transactions; until then the
    caller is responsible for sending.
    """

    def __init__(self, agent_pda_resolver=None) -> None:
        """
        :param agent_pda_resolver: optional callable(agent_id_str) -> Pubkey
            that resolves an ARS agent_id to the agent PDA. Default
            assumes agent_id is already the base58 of the agent PDA.
        """
        self._resolve_agent = agent_pda_resolver or (lambda a: Pubkey.from_string(a))

    async def lock_collateral(
        self,
        job_id: str,
        agent_id: str,
        amount: int,
    ) -> InstructionIntent:
        """
        Realise via `view_bond(min_bond, min_score)`. The Telaro design
        treats the bond as standing collateral rather than per-job lock,
        so `amount` is interpreted as the minimum bond the agent must
        hold for this job to be underwritable.
        """
        params = LockCollateralParams(
            job_id=job_id,
            agent=self._resolve_agent(agent_id),
            min_bond_atomic=amount,
            min_score=0,
        )
        return lock_collateral_intent(params)

    async def slash_collateral(
        self,
        job_id: str,
        agent_id: str,
        payee: str,
        amount: int,
    ) -> InstructionIntent:
        """
        Realise via `resolve_claim` (accept). Caller is expected to have
        already submitted the claim; this builds the resolution.
        """
        raise NotImplementedError(
            "slash_collateral requires a Claim PDA. Construct "
            "SlashCollateralParams directly and call "
            "slash_collateral_intent(); the resolver does not auto-"
            "derive the Claim PDA in v0.1."
        )

    async def unlock_collateral(
        self,
        job_id: str,
        agent_id: str,
    ) -> InstructionIntent:
        raise NotImplementedError(
            "unlock_collateral requires bond_mint, controller, and "
            "controller_bond_ata. Construct UnlockCollateralParams "
            "directly and call unlock_collateral_intent()."
        )

    async def pay_premium(
        self,
        job_id: str,
        payer: str,
        underwriter: str,
        amount: int,
    ) -> InstructionIntent:
        params = PayPremiumParams(
            job_id=job_id,
            payer=Pubkey.from_string(payer),
            underwriter=Pubkey.from_string(underwriter),
            amount_atomic=amount,
        )
        return pay_premium_intent(params)

    async def release_principal(
        self,
        job_id: str,
        agent_id: str,
        amount: int,
    ) -> InstructionIntent:
        raise NotImplementedError(
            "release_principal requires the CreditLine PDA. Derive it "
            "from ['credit-line', agent] and call "
            "release_principal_intent(ReleasePrincipalParams(...))."
        )
