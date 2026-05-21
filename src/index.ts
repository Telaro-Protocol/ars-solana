/**
 * @telaro/ars-solana — the Agentic Risk Standard, implemented for the
 * Telaro Solana program.
 *
 * ARS (github.com/t54-labs/AgenticRiskStandard) splits a job into a fee
 * track and a principal track. Telaro implements the **principal track**
 * — the underwriting + collateral + principal-release lifecycle for
 * agents that handle user capital.
 *
 * This entrypoint exports:
 *  - the principal-track event types (`events.ts`)
 *  - the event-sourced state machine (`state.ts`)
 *  - the `SettlementLayer` contract + telaro instruction map (`settlement.ts`)
 *
 * See docs/internal/ars-dual-track-redesign.md for how this maps onto the
 * on-chain `telaro` program.
 */

export type {
  ArsEvent,
  ArsEventType,
  JobOpened,
  UnderwritingStarted,
  UnderwritingDecided,
  PrincipalReleased,
  EvidenceSubmitted,
  Disputed,
  Closed,
} from "./events.js";

export {
  applyEvent,
  replay,
  isTerminal,
  ARSTransitionError,
  type Job,
  type PrincipalState,
} from "./state.js";

export {
  TELARO_SETTLEMENT_MAP,
  type SettlementLayer,
  type SettlementMethod,
  type SettleResult,
  type TelaroBinding,
} from "./settlement.js";

export {
  lockCollateralIx,
  slashCollateralIx,
  unlockCollateralIx,
  payPremiumIx,
  releasePrincipalIx,
  type LockCollateralParams,
  type SlashCollateralParams,
  type UnlockCollateralParams,
  type PayPremiumParams,
  type ReleasePrincipalParams,
} from "./binding.js";

export {
  TelaroSettlement,
  connectionSender,
  type TxSender,
} from "./client.js";

export { InMemoryEventStore, type EventStore } from "./store.js";

export { toArsEvent, type IngestContext } from "./ingest.js";
