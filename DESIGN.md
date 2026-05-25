# DESIGN: `@telaro/ars-solana`

A one-page design map for the Solana concrete implementation of the
[Agentic Risk Standard](https://github.com/t54-labs/AgenticRiskStandard).
The goal is to satisfy ARS's abstract contracts using an Anchor program
that already runs on Solana devnet, with one deliberate implementation
choice: the underwriter is a program-controlled pool rather than a
keyholder.

This document is the mapping table. The runnable artefact is the npm
package (`npm install @telaro/ars-solana`) and the test suite in this
repo (`pnpm test`). The versioned profile (PDA layout, event schemas,
conformance criteria) is [SPEC.md](SPEC.md).

## Scope

| Track | v1 status | Reason |
| --- | --- | --- |
| Principal track | implemented | Telaro is a capital-risk layer; this is its native job |
| Fee track | out of v1 | Telaro does not run a generic service-fee escrow; would add scope without sharpening the risk story |

Open question for the t54 team: would an ARS concrete implementation
that ships the principal track first (with fee track following) be
acceptable as a `concrete/` upstream, or do you expect both tracks
complete?

## `SettlementLayer` ABC → telaro program

Six of the eight ABC methods map to instructions already live on the
Telaro Anchor program. The two fee-track methods are intentionally not
implemented in v1.

| `SettlementLayer` method | Telaro Anchor instruction | Notes |
| --- | --- | --- |
| `lock_collateral` | `view_bond` | Bond is standing collateral; this checks the standing bond and the per-agent reserved-for-claims accounting. Leverage must stay <= 5x. |
| `slash_collateral` | `resolve_claim` / `arbiter_resolve` | A `ForUser` ruling pays the harmed party out of the agent's bond. |
| `unlock_collateral` | `withdraw_bond` | Released when the job closes, subject to a 30-day withdrawal cooldown. |
| `pay_premium` | `process_pool_yield` / `fund_insurance` | Premium routes to the `UnderwriterPool` (decentralised) or to `InsuranceVault` as a backstop. |
| `release_principal` | `request_credit` | Under-collateralised draw from the `UnderwriterPool`. Agent score must be >= 700. |
| `lock_fee` | (none) | Fee track is out of scope for v1. |
| `release_fee` | (none) | Fee track is out of scope for v1. |
| `refund_fee` | (none) | Fee track is out of scope for v1. |

This table is the same one pinned in [`src/settlement.ts`](src/settlement.ts)
as `TELARO_SETTLEMENT_MAP`, so the doc and the code cannot drift.

## `CollateralVault` ABC → telaro accounts

| `CollateralVault` op | Telaro instruction / account | Notes |
| --- | --- | --- |
| `lock` | `bond_agent`, `top_up_bond` → `BondAccount` PDA | USDC bond, per agent. |
| `unlock` | `withdraw_bond` | 30-day cooldown. |
| `slash` | `resolve_claim` / `arbiter_resolve` | Payout from `BondAccount` to harmed party + reserve. |
| `get_status` | account read on `BondAccount` | `{ locked, available, slashed_to_date }`. |

`DepositStatus { LOCKED, RELEASED, REFUNDED, SLASHED }` is derived
from the bond account and the on-chain claim state.

## The one implementation choice we'd flag

`pay_premium` in the ABC takes an `underwriter` address. The AP2
implementation, as we read it, fills that slot with a designated
keyholder. Since the ABC only treats the underwriter as an address,
the Solana implementation points it at a **program-controlled
`UnderwriterPool`**: a permissionless USDC pool with insurance reserve
backstop. The role becomes protocol-enforced rather than
single-party.

This stays inside the abstract contract; the ABC does not constrain
who or what the underwriter is. We think it is a meaningful addition
for the Web3 setting and would want it reviewed as part of the
contribution.

## Event store

ARS's reference implementation uses a signed SQLite log. Two options
on Solana:

1. **v1: on-chain Anchor events.** Every settlement instruction emits
   a structured event. `src/ingest.ts` maps these to ARS principal-
   track events; `src/state.ts` replays them. This is what the package
   ships today.
2. **v2: signed log + on-chain anchor.** If t54 prefers conformance
   with the reference design, we can run a signed log alongside and
   anchor a Merkle root on-chain.

Open question: do you expect a concrete implementation to use the
signed-SQLite log, or is an on-chain event source acceptable?

## Identity

We do not introduce a Telaro identity layer. The Solana ecosystem has
an [Agent Registry](https://solana.com/agent-registry) that gives
agents on-chain identity in the same three-registry shape as
ERC-8004 (Identity, Reputation, Validation). Telaro publishes bond
state and underwriting verdicts into the Reputation Registry; agents
are identified by their Registry PDA. The Reputation Registry's own
docs name "insurance pools" and "trust-gated marketplaces" as
intended consumers, which is exactly this layer.

## What's not in this repo

- Fee-track concrete (`lock_fee` / `release_fee` / `refund_fee`).
- A Python adapter that exposes this Anchor program through the ARS
  Python ABC. We will write that once the design alignment with t54
  is settled, so the adapter signature matches what gets upstreamed.

## Open questions for the t54 team

1. Principal-track-first as an acceptable shape for a `concrete/`
   contribution, with fee track following.
2. On-chain event source vs the signed SQLite log.
3. Contribution mechanics: external repo referenced from the standard,
   or upstreamed into `concrete/`.
4. Interface-stability expectations on `abstract_ars/` that we should
   design against.
