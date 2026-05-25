# ARS-Solana Profile v0.1

**Status: Draft. Versioning: semantic. v0.x is unstable.**

This document specifies the Solana realization of the
[Agentic Risk Standard](https://github.com/t54-labs/AgenticRiskStandard)
principal track. It is the engineering surface a reader needs to
verify that an implementation satisfies the standard on Solana:
which Anchor instructions back which ABC method, which PDAs hold
which state, and which on-chain events anchor the off-chain log.

The reference implementation that conforms to this profile is
[`@telaro/ars-solana`](https://www.npmjs.com/package/@telaro/ars-solana),
running against the Telaro program at
`3DUrvVWEziYLtEbiDtfxqh1ioXRFX6DNvV4iTsGed2rs` on Solana devnet.

> The mapping in this document is the same one pinned in source at
> [`src/settlement.ts`](src/settlement.ts) as `TELARO_SETTLEMENT_MAP`.
> The spec and the runtime cannot drift.

## 1. Scope and versioning

| Item | v0.1 |
| --- | --- |
| Principal track | In scope. Specified below. |
| Fee track | Deferred to v0.2. See §10. |
| Network | Solana devnet. Mainnet pending audit. |
| Stability | None. v0.x may break across minor versions. v1.0 will pin stability guarantees. |
| Audience | Implementers of the ARS Solana concrete layer. |

Conformance levels:

- **Conformant v0.1**: realizes all six in-scope methods, uses the PDAs
  in §3, emits the events in §4, and meets the invariants in §6.
- **Conformant v0.1 (partial)**: realizes a strict subset of the six
  methods and is honest about which.

## 2. The settlement surface

The ARS abstract layer defines `SettlementLayer` with eight methods
across two tracks. v0.1 specifies the six principal-track methods.
The two fee-track methods are deferred (§10).

| ABC method | v0.1 status | Telaro instruction |
| --- | --- | --- |
| `lock_collateral` | In scope | `view_bond` |
| `slash_collateral` | In scope | `resolve_claim` / `arbiter_resolve` |
| `unlock_collateral` | In scope | `withdraw_bond` |
| `pay_premium` | In scope | `process_pool_yield` / `fund_insurance` |
| `release_principal` | In scope | `request_credit` |
| `lock_fee` | Deferred (v0.2) | n/a |
| `release_fee` | Deferred (v0.2) | n/a |
| `refund_fee` | Deferred (v0.2) | n/a |

Each method is realized by exactly one (or, where noted, one of two
arbitrating paths) Solana instruction, dispatched via the canonical
instruction discriminator. See [`src/binding.ts`](src/binding.ts) for
the pure builders.

### 2.1 `lock_collateral`

Realized by `view_bond(min_bond, min_score)`.

The Telaro design treats bond as standing collateral rather than
per-job lock. `view_bond` evaluates a deterministic policy over the
agent's standing bond and reserved-for-claims accounting. A pass
signals the bond is available for the job's risk envelope. Concrete
checks, in order:

1. `FROZEN`: agent is not frozen.
2. `BOND_BELOW_MIN`: `current_bond >= min_bond`.
3. `SCORE_BELOW_MIN`: `current_score >= min_score`.
4. `OVER_LEVERAGED`: `value_handled_30d <= current_bond * 5`.

Failure on any check reverts the parent transaction atomically.

### 2.2 `slash_collateral`

Realized by `resolve_claim` (a `ForUser` ruling) or `arbiter_resolve`
(an `accept` ruling). Both pay the harmed party out of the agent's
`BondAccount` and may top up the `InsuranceVault` from the same
draw.

### 2.3 `unlock_collateral`

Realized by `withdraw_bond`. The release is gated by:

- A 30-day withdrawal cooldown after the last action.
- Zero open claims against the agent.
- Bond does not drop below `MIN_BOND_USDC`.

### 2.4 `pay_premium`

Realized by `process_pool_yield` (route premium to the
`UnderwriterPool`, the decentralized path) or `fund_insurance`
(route premium to `InsuranceVault`, the backstop path). The choice
is implementation-side; both satisfy the ABC's address-based
underwriter contract.

### 2.5 `release_principal`

Realized by `request_credit(amount)`. Draws against the agent's
`CreditLine` PDA, which is sized by the `UnderwriterPool` and the
agent's score. Agent score must be at least 700.

## 3. PDA layout

All PDAs are derived from the program at
`3DUrvVWEziYLtEbiDtfxqh1ioXRFX6DNvV4iTsGed2rs` with the seeds below.
This list is the authoritative one; the SDK helpers in
[`@telaro/sdk`](https://www.npmjs.com/package/@telaro/sdk) at
`sdk/src/pda.ts` derive against the same seeds.

| PDA | Seeds |
| --- | --- |
| `Agent` | `["agent", controller_pubkey]` |
| `ActionLog` | `["log", agent_pubkey]` |
| `BondVault` | `["vault", agent_pubkey]` |
| `Claim` | `["claim", agent_pubkey, action_hash, claimer_pubkey]` |
| `DepositVault` | `["deposit", claim_pubkey]` |
| `CreditLine` | `["credit-line", agent_pubkey]` |
| `ScoreFeed` | `["score-feed", agent_pubkey]` |
| `PoolConfig` | `["pool-config"]` |
| `PoolVault` | `["pool-vault"]` |
| `PoolStusdcMint` | `["pool-stusdc-mint"]` |
| `PoolMintAuth` | `["pool-mint-auth"]` |
| `ProtocolConfig` | `["protocol-config"]` |
| `InsuranceConfig` | `["insurance-config", bond_mint]` |
| `InsuranceVault` | `["insurance-vault", bond_mint]` |
| `InsuranceAuth` | `["insurance-auth", bond_mint]` |
| `LpPosition` | `["lp-position", agent_pubkey, lp_kind]` |
| `CapRegistry` | `["cap-registry", agent_pubkey]` |
| `TsusdcConfig` | `["tsusdc-config", agent_pubkey]` |
| `TsusdcMint` | `["tsusdc-mint", agent_pubkey]` |
| `TsusdcMintAuth` | `["tsusdc-mint-auth", agent_pubkey]` |

`agent_pubkey` here is itself a PDA (`["agent", controller]`). The
`agent` PDA is the canonical job-subject identifier and the value
used as ARS `agent_id` throughout this profile.

## 4. On-chain events as the principal-track log

The reference ARS uses a signed SQLite log. The Solana profile uses
on-chain Anchor events. Event schemas below are the v0.1
canonicalization; `src/ingest.ts` in `@telaro/ars-solana` maps each
to its ARS event type.

| Anchor event | ARS event(s) | Trigger |
| --- | --- | --- |
| `AgentRegistered` | (off-chain `JobOpened` enrichment) | `init_agent` |
| `ActionRecorded` | `EvidenceSubmitted` | `record_action` |
| `BondTopUp` | (collateral exposure update) | `top_up_bond` |
| `BondWithdrawn` | `CollateralUnlocked` | `withdraw_bond` |
| `ClaimSubmitted` | `DisputeOpened` | `submit_claim` |
| `ClaimResolved` | `CollateralSlashed` or `JobClosed` | `resolve_claim` / `arbiter_resolve` / `arbiter_timeout` |
| `ScoreUpdated` | (score-feed update) | `update_score` / `push_score` |
| `AgentFrozen` | `JobFrozen` | freeze path inside `resolve_claim` |
| `YieldAccrued` | (premium routing record) | `accrue_yield` |
| `CreditDrawn` | `PrincipalReleased` | `request_credit` |
| `CreditRepaid` | `PrincipalRepaid` | `repay_credit` |

A conformant indexer that wants to drive a `replay`-style state
machine should subscribe to these events and route through
`toArsEvent` (or equivalent).

### 4.1 Job identity

`job_id` in the ARS state machine corresponds to the Telaro
`action_hash` of the originating action. Of the on-chain events,
only `ActionRecorded` carries the action hash, so `toArsEvent` maps
it directly. Claim and credit events carry the agent pubkey only;
the caller resolves their job id.

## 5. Conformance test

An implementation is conformant if it can replay the events of any
job from the reference test corpus to the same `Job` state. The
reference corpus is the bankrun integration test suite in the
Telaro program repo
([`programs/telaro/tests/tests/ars-binding.test.ts`](https://github.com/Telaro-Protocol/telaro-protocol/blob/main/programs/telaro/tests/tests/ars-binding.test.ts))
plus the demo at `programs/telaro/tests/tests/ars-lifecycle-demo.ts`.

The reference implementation (`@telaro/ars-solana@^0.1`) passes 37
unit tests for the state machine + event store + ingestion, and 5
bankrun integration tests against the compiled program. Any
conformant implementation should subsume this corpus.

## 6. Invariants

A conformant implementation must satisfy:

1. **Replay determinism.** `replay(events)` is pure. Given the same
   event log, two calls produce identical `Job` states. No external
   reads inside `replay`.
2. **Append-only log.** Events are validated on append. The store
   rejects an event that violates the state machine; it does not
   silently drop or reorder.
3. **Conservation of collateral.** For any agent, the sum across
   time of `slash` plus standing bond plus already-withdrawn bond
   never decreases without a matching on-chain event.
4. **Single underwriter address per pay_premium.** The implementation
   must commit to one of the two underwriter paths
   (`UnderwriterPool` or `InsuranceVault`) per premium routing
   decision. Mixed routing within a single premium is out of scope.
5. **No phantom state.** A `Job` has no field that is not derivable
   from its event log.

## 7. The underwriter choice

The ARS ABC treats the underwriter as an opaque address. The Solana
profile makes this slot a program-controlled account by default:
the `UnderwriterPool`, a permissionless USDC pool with the
`InsuranceVault` as backstop. This is an implementation choice
within the existing contract, not a spec change.

A conformant implementation may instead point the underwriter at a
keyholder, matching the AP2 (EVM) realization. The profile does not
require the program-controlled path; it requires only that whichever
address is chosen, the ABC's address-based contract holds.

## 8. SDK surface

The reference implementation exposes:

```ts
import {
  applyEvent,
  replay,
  TelaroSettlement,
  TELARO_SETTLEMENT_MAP,
  type ArsEvent,
  type Job,
} from "@telaro/ars-solana";
```

The `TelaroSettlement` client realizes the `SettlementLayer`
interface and sends the mapped instructions. The pure builders in
`src/binding.ts` are also exported for callers that own their own
transaction assembly.

## 9. Identity binding

`agent_id` is the agent PDA (`["agent", controller]`). It is stable
across the agent's lifetime and is the value an external system
should use to reference the agent across the principal track. The
controller key is a separate concept (it is the signer authority).

For ecosystem identity composition (Solana Agent Registry,
ERC-8004), the agent PDA is the canonical handle on the Telaro
side. The mapping between an Agent Registry record and a Telaro
agent PDA is a separate spec (planned for v0.2) and is one of the
open questions in §10.

## 10. Open questions

- **Fee track on Solana.** v0.1 omits fee-track methods.
  `lock_fee` / `release_fee` / `refund_fee` will live in v0.2,
  pending decision on whether they share infrastructure with x402
  settlement or introduce a dedicated escrow PDA.
- **Agent Registry binding.** A Reputation Registry write interface
  exists on Solana Agent Registry. The binding spec from a Telaro
  agent PDA into an Agent Registry record is open and tracked at
  [`Telaro-Protocol/telaro-protocol#TBD`](https://github.com/Telaro-Protocol/telaro-protocol/issues).
- **Multi-key separation.** x402 settlement payer key versus Telaro
  agent controller key. v0.1 collapses them; v0.2 will specify the
  separation.
- **Event source choice.** The reference ARS uses a signed SQLite
  log. v0.1 of this profile uses on-chain Anchor events as the
  canonical source. A conformant implementation that wants the
  reference path (signed log anchored on-chain by Merkle root) is
  allowed but is left as future work.

## 11. Changelog

| Version | Date | Notes |
| --- | --- | --- |
| v0.1 | 2026-05-26 | Initial draft. Principal track only. Devnet reference at `3DUrvVWEziYLtEbiDtfxqh1ioXRFX6DNvV4iTsGed2rs`. |

## 12. Maintenance

This profile is maintained at
[Telaro-Protocol/ars-solana](https://github.com/Telaro-Protocol/ars-solana).
Comments, conformance reports, and competing realizations are
welcome at the repo's issue tracker. Upstream coordination with the
ARS abstract layer is tracked at
[t54-labs/AgenticRiskStandard#2](https://github.com/t54-labs/AgenticRiskStandard/issues/2).

License: MIT.
