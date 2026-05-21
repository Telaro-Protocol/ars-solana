# @telaro/ars-solana

**The [Agentic Risk Standard](https://github.com/t54-labs/AgenticRiskStandard)
(ARS), implemented for Solana.**

ARS splits an AI-agent job into a *fee track* and a *principal track*.
`@telaro/ars-solana` implements the **principal track** — the
underwriting → collateral → principal-release lifecycle for agents that
handle user capital — backed by the Telaro program on Solana.

It is the Solana counterpart to ARS's EVM reference implementation: the
ARS abstract layer, instantiated against an on-chain program that
already ships bonding, slashing, a decentralized underwriter pool, and
under-collateralized credit.

## Install

```bash
npm install @telaro/ars-solana
```

## Modules

| Module | Role |
| ------ | ---- |
| `events.ts` | the principal-track event types — the job log is append-only |
| `state.ts` | the event-sourced state machine — `replay()` derives the job |
| `store.ts` | `EventStore` — append-only, validate-on-append event log |
| `ingest.ts` | `toArsEvent` — Telaro on-chain events → ARS events |
| `settlement.ts` | the `SettlementLayer` contract + Telaro instruction map |
| `binding.ts` | ARS settlement actions → Telaro instructions (pure builders) |
| `client.ts` | `TelaroSettlement` — the async client that sends them |

## Lifecycle

A job carries no mutable state of its own — `replay()` folds an
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

An illegal transition throws `ARSTransitionError` — the log can never
fold into an invalid job. `EventStore` (`store.ts`) validates the same
way on append.

## Settlement

`TelaroSettlement` implements the ARS `SettlementLayer` for Solana. Of
the 8 ARS settlement methods, 6 map onto Telaro program instructions
that already exist on-chain; the two `*Fee` methods are out of scope for
v1 — Telaro is a capital-risk layer, not a generic service-fee escrow.

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

Sending is abstracted behind a `TxSender`, so the same client runs
against a live RPC (`connectionSender`) or an in-process test runtime.

## Tests

```bash
pnpm test
```

runs the unit suite (37 tests) — the event-sourced lifecycle, the event
store, on-chain ingestion, and the settlement binding's instruction
shapes (program id, discriminator, accounts).

The settlement binding is additionally verified **end to end against the
real compiled Telaro program** in an in-process Solana runtime (bankrun):
each instruction is sent and the program's acceptance + state change
asserted. That integration test and a narrated lifecycle demo live in
the Telaro program repository.

## Identity

ARS `jobId` is the Telaro `action_hash`. Of the on-chain events, only
`ActionRecorded` carries the action hash, so `toArsEvent` maps it
self-contained; claim and credit events need the job id resolved by the
caller. The off-chain half of the lifecycle (`JobOpened`,
`UnderwritingStarted`/`Decided`) is produced by the settlement layer,
not ingested from chain.

## License

MIT
