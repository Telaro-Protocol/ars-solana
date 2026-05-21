/**
 * ARS principal-track events.
 *
 * Telaro's ARS-Solana implementation is **event-sourced**, mirroring the
 * ARS abstract layer: a job carries no mutable state of its own — its
 * lifecycle state is derived by replaying this append-only event log
 * (see `state.ts`).
 *
 * Why event-sourced (this resolves the open question in
 * docs/internal/ars-dual-track-redesign.md §7): it matches the ARS
 * reference design, makes the principal-track lifecycle auditable, and
 * lets on-chain telaro events (bond, slash, credit draw) and off-chain
 * ARS decisions (the underwriting verdict) feed one ordered log.
 *
 * The principal track is the only track Telaro implements — Telaro is a
 * capital-risk layer, not a generic service-fee escrow (dual-track
 * redesign §4.2).
 */

/** Fields every event carries. */
interface BaseEvent {
  /** ARS job id. On Solana this is the telaro `action_hash` (§4.1). */
  jobId: string;
  /** Unix seconds the event was recorded. */
  at: number;
}

/** A capital-handling job is opened by a DApp delegating to an agent. */
export interface JobOpened extends BaseEvent {
  type: "JobOpened";
  /** Agent wallet — the Telaro agent key / x402 transfer authority. */
  agent: string;
  /** DApp / capital provider that opened the job (ARS Requestor). */
  requestor: string;
  /** Capital the agent will handle for this job (USDC atomic, 6dp). */
  exposureAtomic: bigint;
}

/** Underwriting review has begun (the telaro `view_bond` evaluation). */
export interface UnderwritingStarted extends BaseEvent {
  type: "UnderwritingStarted";
}

/** The underwriting verdict — `view_bond` passed or failed. */
export interface UnderwritingDecided extends BaseEvent {
  type: "UnderwritingDecided";
  passed: boolean;
  /** Gate failure code when `passed` is false (NOT_BONDED, FROZEN, …). */
  failureCode?: string;
}

/** Principal was released to the agent (a `request_credit` draw). */
export interface PrincipalReleased extends BaseEvent {
  type: "PrincipalReleased";
  amountAtomic: bigint;
}

/** The agent's execution result was recorded (telaro `record_action`). */
export interface EvidenceSubmitted extends BaseEvent {
  type: "EvidenceSubmitted";
  /** telaro `action_hash` of the recorded action. */
  actionHash: string;
  outcome: "success" | "failed";
}

/** A claim was filed against the job — hands off to the telaro claim flow. */
export interface Disputed extends BaseEvent {
  type: "Disputed";
  /** telaro `Claim` PDA. */
  claim: string;
}

/** The job reached a terminal outcome. */
export interface Closed extends BaseEvent {
  type: "Closed";
  resolution:
    | "no_dispute" // dispute window expired clean
    | "dispute_upheld" // claim resolved against the agent (bond slashed)
    | "dispute_rejected"; // claim resolved in the agent's favour
}

export type ArsEvent =
  | JobOpened
  | UnderwritingStarted
  | UnderwritingDecided
  | PrincipalReleased
  | EvidenceSubmitted
  | Disputed
  | Closed;

export type ArsEventType = ArsEvent["type"];
