# @telaro/ars-solana

**The [Agentic Risk Standard](https://github.com/t54-labs/AgenticRiskStandard)
(ARS), implemented for Solana.**

ARS splits an AI-agent job into a *fee track* and a *principal track*.
`@telaro/ars-solana` implements the **principal track**: the
underwriting, collateral, and principal-release lifecycle for agents
that handle user capital, backed by the Telaro program on Solana.

It is the Solana counterpart to ARS's EVM reference implementation. The
ARS abstract layer runs against an on-chain program that already ships
bonding, slashing, a decentralized underwriter pool, and
under-collateralized credit.

## Install

```bash
npm install @telaro/ars-solana
```

## 10-second look: the event-sourced job

```ts
import { applyEvent, replay, type ArsEvent } from "@telaro/ars-solana";

const events: ArsEvent[] = [/* fetched from your store or the chain */];
const job = replay(events);

console.log(job.state);     // e.g. "RELEASABLE"
console.log(job.collateral); // standing bond exposure for this job
```

`replay` is pure. There is no mutable job state on disk; the log *is* the
state. See [DESIGN.md](DESIGN.md) for how each method maps to the Telaro
Anchor program.

## Modules

| Module | Role |
| ------ | ---- |
| `events.ts` | Principal-track event types; an append-only job log |
| `state.ts` | Event-sourced state machine; `replay()` derives the job |
| `store.ts` | `EventStore`, an append-only, validate-on-append log |
| `ingest.ts` | `toArsEvent`: maps Telaro on-chain events to ARS events |
| `settlement.ts` | The `SettlementLayer` contract and Telaro instruction map |
| `binding.ts` | ARS settlement actions to Telaro instructions (pure builders) |
| `client.ts` | `TelaroSettlement`, the async client that sends them |

## Lifecycle

A job carries no mutable state of its own. `replay()` folds an
append-only event log into the current job, matching the ARS reference
design.

```
AWAIT_UNDERWRITING → UNDERWRITING → RELEASABLE → EXECUTING
                          │              → EVIDENCE_SUBMITTED
                          │                    → (DISPUTED →) CLOSED
                          └─ REJECTED
```

```ts
import { replay } from "@telaro/ars-solana";

const job = replay([
  { type: "JobOpened", jobId, at, agent, requestor, exposureAtomic },
  { type: "UnderwritingStarted", jobId, at },
  { type: "UnderwritingDecided", jobId, at, passed: true },
  { type: "PrincipalReleased", jobId, at, amountAtomic },
  { type: "EvidenceSubmitted", jobId, at, actionHash, outcome: "success" },
  { type: "Closed", jobId, at, resolution: "no_dispute" },
]);
// job.state === "CLOSED"
```

An illegal transition throws `ARSTransitionError`, so the log can never
fold into an invalid job. `EventStore` (`store.ts`) validates the same
way on append.

## Settlement

`TelaroSettlement` implements the ARS `SettlementLayer` for Solana. Of
the 8 ARS settlement methods, 6 map onto Telaro program instructions
that already exist on-chain. The two `*Fee` methods are out of scope for
v1, since Telaro is a capital-risk layer, not a generic service-fee
escrow.

| ARS method | Telaro instruction |
| ---------- | ------------------ |
| `lockCollateral` | `view_bond` |
| `slashCollateral` | `resolve_claim` |
| `unlockCollateral` | `withdraw_bond` |
| `payPremium` | `process_pool_yield` |
| `releasePrincipal` | `request_credit` |

```ts
import { TelaroSettlement, connectionSender } from "@telaro/ars-solana";

const settlement = new TelaroSettlement({ sender: connectionSender(connection) });
const { signature } = await settlement.releasePrincipal(
  { jobId, agent, controller, amountAtomic },
  [controllerKeypair], // signers, fee payer first
);
```

Sending goes through a `TxSender`, so the same client runs against a
live RPC (`connectionSender`) or an in-process test runtime.

## Tests

```bash
pnpm test
```

runs the unit suite (37 tests): the event-sourced lifecycle, the event
store, on-chain ingestion, and the settlement binding's instruction
shapes (program id, discriminator, accounts).

The settlement binding is also verified **end to end against the real
compiled Telaro program** in an in-process Solana runtime (bankrun):
each instruction is sent, and both the program's acceptance and the
resulting state change are asserted. That integration test and a
narrated lifecycle demo live in the Telaro program repository.

## Design

The one-page mapping from the ARS abstract layer to the Telaro Anchor
program is in [DESIGN.md](DESIGN.md). The full versioned profile is
[SPEC.md](SPEC.md): **ARS-Solana Profile v0.1** (PDA layout, event
schemas, conformance criteria, invariants). This package is the
reference implementation for the profile.

A Python adapter that satisfies the same ARS abstract base classes
against the Telaro Anchor program lives at [python/](python/) in this
repo (`pip install telaro-ars` once published). It mirrors the TS
state machine line for line; the conformance test corpus replays in
both languages.

## Identity

ARS `jobId` is the Telaro `action_hash`. Of the on-chain events, only
`ActionRecorded` carries the action hash, so `toArsEvent` can map it on
its own. Claim and credit events need the job id resolved by the caller.
The off-chain half of the lifecycle (`JobOpened`,
`UnderwritingStarted` and `UnderwritingDecided`) is produced by the
settlement layer, not ingested from chain.

## License

MIT
