"""
Tests for the Python x402 gate.

Covers the gate's decision logic for each `GateResult` arm, and the
parser's behaviour on missing or malformed inputs. The Solana
transaction parsing path is exercised with constructed legacy
transactions because solders accepts those without a chain.
"""

import base64
import json

import pytest

from telaro_ars.x402 import (
    GateFail,
    GatePass,
    GatePolicy,
    GateUnusable,
    apply_x402_gate,
    status_for_code,
)


def _encode_header(serialized_tx_b64: str) -> str:
    """Helper: produce a valid X-PAYMENT header value around a tx."""
    envelope = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "solana-devnet",
        "payload": {"serializedTransaction": serialized_tx_b64},
    }
    return base64.b64encode(json.dumps(envelope).encode("utf-8")).decode("utf-8")


def _build_payment(payer_pubkey: str) -> str:
    """Build a one-instruction SPL-transfer-like tx with `payer_pubkey`
    as the signing authority. We accept that solders can decode a
    minimal handcrafted tx; the gate only needs to extract the signing
    account, not actually move tokens."""
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.hash import Hash
    from solders.message import Message
    from solders.transaction import Transaction
    from solders.instruction import Instruction, AccountMeta

    # We replace the payer key inside the resulting tx after build by
    # forcing the signed account to be a known generated keypair, then
    # reporting its pubkey. We can't sign with an arbitrary string, so
    # tests pass a Keypair and we use its pubkey as the payer.
    payer_kp = Keypair.from_seed(bytes(32))  # deterministic
    # The caller passes payer_pubkey as a hint, but in this builder
    # the actual signing key is `payer_kp`. The test uses the kp's
    # base58 as the payer identity.
    del payer_pubkey

    spl_program = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
    src_ata = Keypair().pubkey()
    mint = Keypair().pubkey()
    dst_ata = Keypair().pubkey()

    ix = Instruction(
        program_id=spl_program,
        accounts=[
            AccountMeta(pubkey=src_ata, is_signer=False, is_writable=True),
            AccountMeta(pubkey=mint, is_signer=False, is_writable=False),
            AccountMeta(pubkey=dst_ata, is_signer=False, is_writable=True),
            AccountMeta(pubkey=payer_kp.pubkey(), is_signer=True, is_writable=False),
        ],
        data=b"\x03" + (100).to_bytes(8, "little") + b"\x06",
    )

    msg = Message.new_with_blockhash([ix], payer_kp.pubkey(), Hash.default())
    tx = Transaction([payer_kp], msg, Hash.default())
    raw = bytes(tx)
    serialized = base64.b64encode(raw).decode("utf-8")
    return serialized, str(payer_kp.pubkey())


def _payment_for_real_payer() -> tuple[str, str]:
    """Build a payment and return the header value + the payer pubkey
    that the gate will see when it parses it."""
    serialized, payer = _build_payment("placeholder")
    header = _encode_header(serialized)
    return header, payer


# -------------------------------------------------------------------- #
#  Gate-result tests.                                                    #
# -------------------------------------------------------------------- #


def test_missing_header_returns_NO_PAYMENT():
    result = apply_x402_gate(
        None,
        GatePolicy(min_bond_atomic=1, min_score=0),
        lookup_profile=lambda _p: {},
    )
    assert isinstance(result, GateUnusable)
    assert result.code == "NO_PAYMENT"
    assert status_for_code(result.code) == 402


def test_garbage_header_returns_MALFORMED_PAYMENT():
    result = apply_x402_gate(
        "not-a-valid-base64-encoded-envelope",
        GatePolicy(min_bond_atomic=1, min_score=0),
        lookup_profile=lambda _p: {},
    )
    assert isinstance(result, GateUnusable)
    assert result.code == "MALFORMED_PAYMENT"


def test_empty_payload_returns_MALFORMED_PAYMENT():
    envelope = {"x402Version": 1, "scheme": "exact", "payload": {}}
    header = base64.b64encode(json.dumps(envelope).encode()).decode()
    result = apply_x402_gate(
        header,
        GatePolicy(min_bond_atomic=1, min_score=0),
        lookup_profile=lambda _p: {},
    )
    assert isinstance(result, GateUnusable)
    assert result.code == "MALFORMED_PAYMENT"


def test_passing_policy_returns_GatePass():
    header, payer = _payment_for_real_payer()
    result = apply_x402_gate(
        header,
        GatePolicy(min_bond_atomic=100, min_score=500),
        lookup_profile=lambda _p: {
            "score": 800,
            "bond_atomic": 1_000_000_000,
            "frozen": False,
        },
    )
    assert isinstance(result, GatePass)
    assert result.payer == payer
    assert result.profile["score"] == 800


def test_low_score_returns_SCORE_BELOW_MIN():
    header, payer = _payment_for_real_payer()
    result = apply_x402_gate(
        header,
        GatePolicy(min_bond_atomic=1, min_score=700),
        lookup_profile=lambda _p: {
            "score": 500,
            "bond_atomic": 1_000_000_000,
            "frozen": False,
        },
    )
    assert isinstance(result, GateFail)
    assert result.code == "SCORE_BELOW_MIN"
    assert result.payer == payer
    assert status_for_code(result.code) == 403


def test_low_bond_returns_BOND_BELOW_MIN():
    header, payer = _payment_for_real_payer()
    result = apply_x402_gate(
        header,
        GatePolicy(min_bond_atomic=1_000_000_000_000, min_score=0),
        lookup_profile=lambda _p: {
            "score": 800,
            "bond_atomic": 1_000_000,
            "frozen": False,
        },
    )
    assert isinstance(result, GateFail)
    assert result.code == "BOND_BELOW_MIN"


def test_frozen_agent_returns_FROZEN():
    header, payer = _payment_for_real_payer()
    result = apply_x402_gate(
        header,
        GatePolicy(min_bond_atomic=1, min_score=0),
        lookup_profile=lambda _p: {
            "score": 800,
            "bond_atomic": 1_000_000_000,
            "frozen": True,
        },
    )
    assert isinstance(result, GateFail)
    assert result.code == "FROZEN"


def test_unknown_agent_returns_NOT_BONDED():
    header, payer = _payment_for_real_payer()
    result = apply_x402_gate(
        header,
        GatePolicy(min_bond_atomic=1, min_score=0),
        lookup_profile=lambda _p: None,
    )
    assert isinstance(result, GateFail)
    assert result.code == "NOT_BONDED"


def test_lookup_exception_returns_LOOKUP_FAILED():
    header, payer = _payment_for_real_payer()

    def raising_lookup(_p):
        raise RuntimeError("indexer offline")

    result = apply_x402_gate(
        header,
        GatePolicy(min_bond_atomic=1, min_score=0),
        lookup_profile=raising_lookup,
    )
    assert isinstance(result, GateFail)
    assert result.code == "LOOKUP_FAILED"
    assert status_for_code(result.code) == 502


def test_status_for_code_table():
    assert status_for_code("NO_PAYMENT") == 402
    assert status_for_code("MALFORMED_PAYMENT") == 402
    assert status_for_code("NO_TRANSFER") == 402
    assert status_for_code("UNSIGNED_PAYER") == 402
    assert status_for_code("LOOKUP_FAILED") == 502
    assert status_for_code("BOND_BELOW_MIN") == 403
    assert status_for_code("SCORE_BELOW_MIN") == 403
    assert status_for_code("FROZEN") == 403
    assert status_for_code("NOT_BONDED") == 403
