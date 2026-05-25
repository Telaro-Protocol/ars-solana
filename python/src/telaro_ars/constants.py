"""Pinned constants from the Telaro Anchor program."""

from solders.pubkey import Pubkey

# The Telaro program on Solana devnet. Mainnet pending audit.
PROGRAM_ID_DEVNET: Pubkey = Pubkey.from_string(
    "3DUrvVWEziYLtEbiDtfxqh1ioXRFX6DNvV4iTsGed2rs"
)

# Protocol floor on the bond, in atomic USDC (6 decimals).
MIN_BOND_USDC_ATOMIC: int = 1_000_000  # 1 USDC

# Score floor for `release_principal` (a `request_credit` draw).
MIN_SCORE_FOR_CREDIT: int = 700

# Aggregate leverage cap inside `view_bond`.
MAX_LEVERAGE_RATIO: int = 5
