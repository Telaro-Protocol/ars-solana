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
from telaro_ars import (
    PayPremiumParams,
    ReleasePrincipalParams,
    build_resolve_claim_ix,
    build_withdraw_bond_ix,
    build_process_pool_yield_ix,
    build_request_credit_ix,
)
from telaro_ars.pda import (
    bond_vault_pda,
    credit_line_pda,
    deposit_vault_pda,
    pool_config_pda,
    pool_mint_auth_pda,
    pool_vault_pda,
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
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


# -------------------------------------------------------------------- #
#  v0.2: encoded builders for the remaining four methods.               #
# -------------------------------------------------------------------- #


def _disc(name: str) -> bytes:
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]


def test_resolve_claim_layout():
    ix = build_resolve_claim_ix(
        SlashCollateralParams(
            job_id="j",
            claim=_AGENT,
            agent=_AGENT,
            bond_mint=_AGENT,
            claimer_bond_ata=_AGENT,
            signer=_AGENT,
        ),
        action=0,
    )
    assert ix.data[:8] == _disc("resolve_claim")
    assert ix.data[8] == 0  # action byte
    # 8 accounts: claim, agent, mint, vault, deposit, claimer_ata, signer, token_program
    assert len(ix.accounts) == 8
    # signer is account #6 (0-indexed) and is_signer
    signers = [(i, a) for i, a in enumerate(ix.accounts) if a.is_signer]
    assert len(signers) == 1
    assert signers[0][0] == 6
    # last is token program
    assert ix.accounts[7].pubkey == TOKEN_PROGRAM_ID


def test_resolve_claim_derives_bond_and_deposit_pda():
    ix = build_resolve_claim_ix(
        SlashCollateralParams(
            job_id="j",
            claim=_AGENT,
            agent=_AGENT,
            bond_mint=_AGENT,
            claimer_bond_ata=_AGENT,
            signer=_AGENT,
        )
    )
    expected_vault, _ = bond_vault_pda(_AGENT)
    expected_deposit, _ = deposit_vault_pda(_AGENT)
    # vault is account 3, deposit is account 4
    assert ix.accounts[3].pubkey == expected_vault
    assert ix.accounts[4].pubkey == expected_deposit


def test_resolve_claim_rejects_bad_action():
    with pytest.raises(ValueError):
        build_resolve_claim_ix(
            SlashCollateralParams(
                job_id="j",
                claim=_AGENT,
                agent=_AGENT,
                bond_mint=_AGENT,
                claimer_bond_ata=_AGENT,
                signer=_AGENT,
            ),
            action=300,  # > u8
        )


def test_withdraw_bond_layout():
    ix = build_withdraw_bond_ix(
        UnlockCollateralParams(
            job_id="j",
            agent=_AGENT,
            bond_mint=_AGENT,
            controller=_AGENT,
            controller_bond_ata=_AGENT,
            amount_atomic=42,
        )
    )
    assert ix.data[:8] == _disc("withdraw_bond")
    # 8-byte u64 LE
    assert len(ix.data) == 16
    amount = int.from_bytes(ix.data[8:16], "little")
    assert amount == 42
    # 6 accounts: agent, mint, vault, controller_ata, controller(signer), token
    assert len(ix.accounts) == 6
    assert ix.accounts[4].is_signer  # controller signs
    assert ix.accounts[5].pubkey == TOKEN_PROGRAM_ID


def test_process_pool_yield_layout():
    ix = build_process_pool_yield_ix(
        PayPremiumParams(
            job_id="j",
            payer=_AGENT,
            underwriter=_AGENT,
            amount_atomic=1_000_000,
        )
    )
    assert ix.data[:8] == _disc("process_pool_yield")
    assert int.from_bytes(ix.data[8:16], "little") == 1_000_000
    # 5 accounts: pool, vault, source, payer, token
    assert len(ix.accounts) == 5
    pool, _ = pool_config_pda()
    vault, _ = pool_vault_pda()
    assert ix.accounts[0].pubkey == pool
    assert ix.accounts[1].pubkey == vault
    assert ix.accounts[3].is_signer  # payer signs


def test_request_credit_layout():
    controller = Pubkey.from_string("CWz9b8g4h78ytQnd4gEU9qk4fP1wtQjfa7L838HtKNps")
    ix = build_request_credit_ix(
        ReleasePrincipalParams(
            job_id="j",
            agent=_AGENT,
            credit_line=_AGENT,  # unused by builder; recomputed
            amount_atomic=500_000_000,
        ),
        controller=controller,
    )
    assert ix.data[:8] == _disc("request_credit")
    assert int.from_bytes(ix.data[8:16], "little") == 500_000_000
    # 9 accounts: agent, credit_line, bond_vault, pool, pool_vault, pool_mint_auth, controller, token, system
    assert len(ix.accounts) == 9
    cl, _ = credit_line_pda(_AGENT)
    bv, _ = bond_vault_pda(_AGENT)
    pool, _ = pool_config_pda()
    pv, _ = pool_vault_pda()
    pma, _ = pool_mint_auth_pda()
    assert ix.accounts[1].pubkey == cl
    assert ix.accounts[2].pubkey == bv
    assert ix.accounts[3].pubkey == pool
    assert ix.accounts[4].pubkey == pv
    assert ix.accounts[5].pubkey == pma
    assert ix.accounts[6].pubkey == controller
    assert ix.accounts[6].is_signer
    assert ix.accounts[7].pubkey == TOKEN_PROGRAM_ID
    assert ix.accounts[8].pubkey == SYSTEM_PROGRAM_ID


def test_request_credit_default_controller_is_agent():
    # When controller isn't given, falls back to params.agent (caller
    # should usually pass explicitly).
    ix = build_request_credit_ix(
        ReleasePrincipalParams(
            job_id="j",
            agent=_AGENT,
            credit_line=_AGENT,
            amount_atomic=1,
        )
    )
    assert ix.accounts[6].pubkey == _AGENT


def test_u64_amount_overflow_rejected():
    with pytest.raises(ValueError):
        build_withdraw_bond_ix(
            UnlockCollateralParams(
                job_id="j",
                agent=_AGENT,
                bond_mint=_AGENT,
                controller=_AGENT,
                controller_bond_ata=_AGENT,
                amount_atomic=2**64,  # overflow
            )
        )
