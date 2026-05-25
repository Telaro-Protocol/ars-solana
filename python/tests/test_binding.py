"""
Conformance checks for the on-chain binding.

The encoded `view_bond` instruction must byte-match the TypeScript
reference (`buildViewBondIx` in `@telaro/sdk`). The check is exact:
discriminator bytes, u64-LE bond, u16-LE score, account ordering.
"""

import hashlib

import pytest
from solders.pubkey import Pubkey

from telaro_ars import (
    LockCollateralParams,
    PROGRAM_ID_DEVNET,
    SlashCollateralParams,
    UnlockCollateralParams,
    build_view_bond_ix,
    lock_collateral_intent,
    slash_collateral_intent,
    unlock_collateral_intent,
)
from telaro_ars.binding import (
    build_resolve_claim_ix,
    build_request_credit_ix,
)


# The agent PDA from one of the TS test fixtures.
_AGENT = Pubkey.from_string("4Nd1mYJgC7DsB3v9pkM9CRZxoUTfXn1kbm1zFM5hZRgM")


def test_view_bond_discriminator_matches_anchor_rule():
    expected = hashlib.sha256(b"global:view_bond").digest()[:8]
    ix = build_view_bond_ix(
        LockCollateralParams(
            job_id="j", agent=_AGENT, min_bond_atomic=0, min_score=0
        )
    )
    assert ix.data[:8] == expected


def test_view_bond_data_layout_18_bytes():
    ix = build_view_bond_ix(
        LockCollateralParams(
            job_id="j",
            agent=_AGENT,
            min_bond_atomic=1_000_000_000,  # 1000 USDC
            min_score=700,
        )
    )
    # 8 byte disc + 8 byte u64 LE + 2 byte u16 LE
    assert len(ix.data) == 18
    bond = int.from_bytes(ix.data[8:16], "little")
    score = int.from_bytes(ix.data[16:18], "little")
    assert bond == 1_000_000_000
    assert score == 700


def test_view_bond_account_layout():
    ix = build_view_bond_ix(
        LockCollateralParams(
            job_id="j", agent=_AGENT, min_bond_atomic=1, min_score=1
        )
    )
    assert len(ix.accounts) == 1
    a = ix.accounts[0]
    assert a.pubkey == _AGENT
    assert a.is_signer is False
    assert a.is_writable is False


def test_view_bond_program_id_defaults_to_devnet():
    ix = build_view_bond_ix(
        LockCollateralParams(
            job_id="j", agent=_AGENT, min_bond_atomic=1, min_score=1
        )
    )
    assert ix.program_id == PROGRAM_ID_DEVNET


def test_view_bond_rejects_out_of_range_score():
    with pytest.raises(ValueError):
        build_view_bond_ix(
            LockCollateralParams(
                job_id="j",
                agent=_AGENT,
                min_bond_atomic=1,
                min_score=70000,  # > u16
            )
        )


def test_intent_lock_collateral_reports_view_bond():
    intent = lock_collateral_intent(
        LockCollateralParams(
            job_id="j", agent=_AGENT, min_bond_atomic=1, min_score=700
        )
    )
    assert intent.method == "view_bond"
    assert intent.args == {"min_bond": 1, "min_score": 700}
    assert len(intent.accounts) == 1


def test_intent_slash_reports_resolve_claim_accept():
    intent = slash_collateral_intent(
        SlashCollateralParams(
            job_id="j",
            claim=_AGENT,
            agent=_AGENT,
            bond_mint=_AGENT,
            claimer_bond_ata=_AGENT,
            signer=_AGENT,
        )
    )
    assert intent.method == "resolve_claim"
    assert intent.args == {"action": 0}
    # Signer is the controller (account index 4).
    signers = [a for a in intent.accounts if a[2]]
    assert len(signers) == 1
    assert signers[0][0] == "signer"


def test_intent_unlock_reports_withdraw_bond_with_amount():
    intent = unlock_collateral_intent(
        UnlockCollateralParams(
            job_id="j",
            agent=_AGENT,
            bond_mint=_AGENT,
            controller=_AGENT,
            controller_bond_ata=_AGENT,
            amount_atomic=5_000_000,
        )
    )
    assert intent.method == "withdraw_bond"
    assert intent.args == {"amount": 5_000_000}


def test_v0_2_builders_raise_not_implemented():
    with pytest.raises(NotImplementedError, match="v0.2"):
        build_resolve_claim_ix()
    with pytest.raises(NotImplementedError, match="v0.2"):
        build_request_credit_ix()
