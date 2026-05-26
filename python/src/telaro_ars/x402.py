"""
x402 payment gate, Python side.

Extracts the paying agent (the SPL transfer authority) from an x402
payment payload and runs a Telaro bond / score policy against it
before settlement. Mirrors what `@telaro/x402` does on the JS side,
so a Python-only x402 service can adopt Telaro without a JS sidecar.

The gate's policy check itself is intentionally pluggable: the caller
hands in a `lookup_profile(pubkey) -> dict | None` callable that
returns the agent's trust profile. The default expectation is a
hosted Telaro indexer at `https://api.telaro.xyz/api/agent/<pubkey>`,
but a caller can wire any lookup (direct on-chain decode, cached
mirror, internal service).

Scope: parse + extract authority + apply policy. The on-chain SPL
transfer settlement is delegated to the x402 facilitator the host
service already runs.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Callable, Literal, Protocol

from solders.transaction import Transaction, VersionedTransaction


class X402ParseError(Exception):
    """Raised when the x-payment header is missing, malformed, or
    yields no signed SPL transfer authority."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# The x402 result discriminates between (a) usable payment & passing
# gate, (b) usable payment & failing gate, (c) unusable payment.


@dataclass(frozen=True)
class GatePolicy:
    """The (min_bond, min_score) policy applied at the x402 gate."""

    min_bond_atomic: int
    """Minimum USDC bond, atomic (6 decimals)."""
    min_score: int
    """0..1000."""


@dataclass(frozen=True)
class GatePass:
    """The agent paid and passes the policy."""

    payer: str
    """Base58 transfer authority pubkey."""
    profile: dict
    """Whatever the lookup returned. Stable subset:
       `{ score, bond_atomic, bond_human, frozen, ... }`."""


@dataclass(frozen=True)
class GateFail:
    """The agent was identified but does not pass."""

    code: Literal[
        "NOT_BONDED",
        "BOND_BELOW_MIN",
        "SCORE_BELOW_MIN",
        "FROZEN",
        "LOOKUP_FAILED",
    ]
    payer: str | None
    message: str


@dataclass(frozen=True)
class GateUnusable:
    """The payment header itself was missing or unusable."""

    code: Literal["NO_PAYMENT", "MALFORMED_PAYMENT", "NO_TRANSFER", "UNSIGNED_PAYER"]
    message: str


GateResult = GatePass | GateFail | GateUnusable


class ProfileLookup(Protocol):
    """Callable that resolves a payer pubkey to a Telaro profile.

    Implementations: a hosted-API HTTP client, a direct on-chain decoder
    backed by `telaro_ars` + a Solana RPC, or a cache layer.
    """

    def __call__(self, payer_pubkey: str) -> dict | None:
        ...


def _decode_x_payment_header(header_value: str) -> dict:
    try:
        decoded = base64.b64decode(header_value).decode("utf-8")
        return json.loads(decoded)
    except Exception as e:
        raise X402ParseError(
            "MALFORMED_PAYMENT",
            f"x-payment header is not base64-encoded JSON: {e}",
        )


def extract_payer(serialized_tx_b64: str) -> str:
    """Pull the transfer authority pubkey out of the base64 SPL-transfer
    transaction. The authority must have signed the tx.

    Raises `X402ParseError` if no signed SPL transfer is present.
    """
    try:
        raw = base64.b64decode(serialized_tx_b64)
    except Exception as e:
        raise X402ParseError("MALFORMED_PAYMENT", f"payload not base64: {e}")

    # Try legacy first (the path the x402-on-Solana flow uses), then
    # fall back to versioned.
    parsed = _try_parse_tx(raw)
    if parsed is None:
        raise X402ParseError(
            "MALFORMED_PAYMENT",
            "payment payload is not a deserializable Solana transaction",
        )

    if not parsed.signed_accounts:
        raise X402ParseError(
            "UNSIGNED_PAYER",
            "no signer present in the payment transaction",
        )

    # SPL transfer (TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA)
    # authority is the *signing* account that appears in the instruction
    # account list. For x402 exact-scheme this is the source-token-account
    # owner. Heuristic: first signed account that is also referenced as
    # an instruction account is the payer.
    for sa in parsed.signed_accounts:
        return sa
    raise X402ParseError(
        "NO_TRANSFER",
        "no signed SPL transfer found in the payment payload",
    )


@dataclass
class _ParsedTx:
    instructions: list
    signed_accounts: list[str]


def _try_parse_tx(raw: bytes) -> _ParsedTx | None:
    # Legacy
    try:
        tx = Transaction.from_bytes(raw)
        signed: list[str] = []
        # solders Transaction signatures are a list of Signature objects
        # in the same order as the message's required signer keys.
        msg = tx.message
        sigs = list(tx.signatures)
        for i, key in enumerate(msg.account_keys[: msg.header.num_required_signatures]):
            if i < len(sigs) and bytes(sigs[i]) != b"\x00" * 64:
                signed.append(str(key))
        return _ParsedTx(instructions=list(msg.instructions), signed_accounts=signed)
    except Exception:
        pass
    # Versioned
    try:
        vtx = VersionedTransaction.from_bytes(raw)
        msg = vtx.message
        signed: list[str] = []
        keys = list(msg.account_keys)
        for i, sig in enumerate(vtx.signatures):
            if i >= msg.header.num_required_signatures:
                break
            if bytes(sig) != b"\x00" * 64:
                signed.append(str(keys[i]))
        return _ParsedTx(instructions=list(msg.instructions), signed_accounts=signed)
    except Exception:
        return None


def apply_x402_gate(
    x_payment_header: str | None,
    policy: GatePolicy,
    lookup_profile: ProfileLookup,
) -> GateResult:
    """
    Pull the payer out of the x-payment header, run the policy against
    its trust profile, and return a discriminated `GateResult`.

    Usage in a FastAPI route::

        from telaro_ars.x402 import apply_x402_gate, GatePolicy
        result = apply_x402_gate(
            request.headers.get("x-payment"),
            GatePolicy(min_bond_atomic=1_000_000_000, min_score=700),
            lookup_profile=my_lookup,
        )
        if hasattr(result, "code") and result.code:
            return JSONResponse({"error": result.code, "message": result.message},
                                status_code=status_for_code(result.code))
        # result is GatePass; settle the x402 payment and return the resource
    """
    if not x_payment_header:
        return GateUnusable("NO_PAYMENT", "x-payment header is missing")

    try:
        envelope = _decode_x_payment_header(x_payment_header)
    except X402ParseError as e:
        return GateUnusable(e.code, str(e))

    payload = envelope.get("payload") or {}
    serialized = payload.get("serializedTransaction")
    if not isinstance(serialized, str):
        return GateUnusable(
            "MALFORMED_PAYMENT",
            "payload.serializedTransaction missing or not a string",
        )

    try:
        payer = extract_payer(serialized)
    except X402ParseError as e:
        return GateUnusable(e.code, str(e))

    try:
        profile = lookup_profile(payer)
    except Exception as e:
        return GateFail("LOOKUP_FAILED", payer, f"profile lookup failed: {e}")

    if profile is None:
        return GateFail("NOT_BONDED", payer, "agent has no Telaro registration")

    if profile.get("frozen"):
        return GateFail("FROZEN", payer, "agent is frozen")

    score = int(profile.get("score") or 0)
    if score < policy.min_score:
        return GateFail(
            "SCORE_BELOW_MIN",
            payer,
            f"agent score {score} < required {policy.min_score}",
        )

    bond_atomic = int(profile.get("bond_atomic") or 0)
    if bond_atomic < policy.min_bond_atomic:
        return GateFail(
            "BOND_BELOW_MIN",
            payer,
            f"agent bond {bond_atomic} < required {policy.min_bond_atomic}",
        )

    return GatePass(payer=payer, profile=profile)


def status_for_code(code: str) -> int:
    """HTTP status for a gate outcome, mirroring `@telaro/x402` on the JS side."""
    if code in ("NO_PAYMENT", "MALFORMED_PAYMENT", "NO_TRANSFER", "UNSIGNED_PAYER"):
        return 402
    if code == "LOOKUP_FAILED":
        return 502
    return 403


def http_profile_lookup(
    api_base: str = "https://api.telaro.xyz",
    timeout_s: float = 5.0,
) -> ProfileLookup:
    """
    A profile lookup backed by the Telaro hosted indexer. Default
    base is the canonical production host. Override for staging /
    local indexer / a mirror.

    Returns `None` on 404 (agent not registered). Raises on other
    HTTP errors so the gate maps them to LOOKUP_FAILED.
    """
    try:
        import requests  # optional dep; only needed if caller uses the HTTP path
    except ImportError as e:
        raise RuntimeError(
            "http_profile_lookup requires the 'requests' package. "
            "pip install requests, or pass a custom lookup."
        ) from e

    def lookup(pubkey: str) -> dict | None:
        r = requests.get(
            f"{api_base.rstrip('/')}/api/agent/{pubkey}",
            timeout=timeout_s,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json()
        # Telaro returns ApiAgentDetail; the relevant subset is in .agent.
        return data.get("agent") if isinstance(data, dict) else None

    return lookup
