"""
PDA derivation for the Telaro Anchor program.

Seeds are pinned to SPEC.md §3 and match the SDK helpers in
`@telaro/sdk` at `sdk/src/pda.ts`. The Python and TypeScript sides
derive against the same seed list, so an address computed here
will match one computed in TS for the same inputs.
"""

from __future__ import annotations

from solders.pubkey import Pubkey

from telaro_ars.constants import PROGRAM_ID_DEVNET


def find_program_address(
    seeds: list[bytes], program_id: Pubkey = PROGRAM_ID_DEVNET
) -> tuple[Pubkey, int]:
    """Wrap solders' find_program_address into a uniform helper."""
    return Pubkey.find_program_address(seeds, program_id)


def agent_pda(
    controller: Pubkey, program_id: Pubkey = PROGRAM_ID_DEVNET
) -> tuple[Pubkey, int]:
    return find_program_address([b"agent", bytes(controller)], program_id)


def bond_vault_pda(
    agent: Pubkey, program_id: Pubkey = PROGRAM_ID_DEVNET
) -> tuple[Pubkey, int]:
    return find_program_address([b"vault", bytes(agent)], program_id)


def deposit_vault_pda(
    claim: Pubkey, program_id: Pubkey = PROGRAM_ID_DEVNET
) -> tuple[Pubkey, int]:
    return find_program_address([b"deposit", bytes(claim)], program_id)


def credit_line_pda(
    agent: Pubkey, program_id: Pubkey = PROGRAM_ID_DEVNET
) -> tuple[Pubkey, int]:
    return find_program_address([b"credit-line", bytes(agent)], program_id)


def pool_config_pda(
    program_id: Pubkey = PROGRAM_ID_DEVNET,
) -> tuple[Pubkey, int]:
    return find_program_address([b"pool-config"], program_id)


def pool_vault_pda(
    program_id: Pubkey = PROGRAM_ID_DEVNET,
) -> tuple[Pubkey, int]:
    return find_program_address([b"pool-vault"], program_id)


def pool_mint_auth_pda(
    program_id: Pubkey = PROGRAM_ID_DEVNET,
) -> tuple[Pubkey, int]:
    return find_program_address([b"pool-mint-auth"], program_id)


def score_feed_pda(
    agent: Pubkey, program_id: Pubkey = PROGRAM_ID_DEVNET
) -> tuple[Pubkey, int]:
    return find_program_address([b"score-feed", bytes(agent)], program_id)


# Token program (SPL).
TOKEN_PROGRAM_ID: Pubkey = Pubkey.from_string(
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
)

# Solana system program.
SYSTEM_PROGRAM_ID: Pubkey = Pubkey.from_string(
    "11111111111111111111111111111111"
)
