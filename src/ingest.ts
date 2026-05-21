/**
 * On-chain ingestion — telaro program events → ARS principal-track events.
 *
 * `toArsEvent` translates a decoded telaro event into the ARS event it
 * corresponds to, so an indexer can feed the *on-chain half* of a job's
 * lifecycle into the event store. The off-chain half — `JobOpened`,
 * `UnderwritingStarted`/`Decided` — is produced by the ARS settlement
 * layer, not ingested from chain.
 *
 * Job id: ARS `jobId` is the telaro `action_hash` (dual-track redesign
 * §4.1). Only `ActionRecorded` carries the action_hash in its event
 * payload, so it maps self-contained. Claim and credit events reference
 * an agent or a claim PDA but not the action_hash — mapping them needs
 * the job id resolved by the caller (e.g. an indexer that read the
 * `Claim` account) and supplied as `ctx.jobId`.
 *
 * `toArsEvent` returns `null` when the telaro event has no principal-track
 * analogue (bond top-ups, score updates, yield routing, …) **or** when a
 * claim/credit event was passed without `ctx.jobId`.
 */

import type { DecodedEventPayload } from "@telaro/sdk";
import type { ArsEvent } from "./events.js";

export interface IngestContext {
  /** Unix seconds for the produced ARS event — the on-chain block time. */
  at: number;
  /**
   * ARS job id (telaro `action_hash`, hex) for claim/credit events whose
   * payload does not carry it. Ignored for `ActionRecorded`, which
   * derives the job id from its own `actionHash`.
   */
  jobId?: string;
}

const hex = (bytes: Uint8Array): string => Buffer.from(bytes).toString("hex");

/**
 * telaro `ClaimStatus` → ARS `Closed` resolution. Builder-reject (3) and
 * arbiter-for-builder (7) clear the agent; every other resolved status
 * paid the claim out of the bond.
 */
function claimStatusResolution(
  status: number
): "dispute_upheld" | "dispute_rejected" {
  return status === 3 || status === 7 ? "dispute_rejected" : "dispute_upheld";
}

/** Map one decoded telaro event to an ARS event, or `null` (see file doc). */
export function toArsEvent(
  payload: DecodedEventPayload,
  ctx: IngestContext
): ArsEvent | null {
  switch (payload.name) {
    case "ActionRecorded": {
      // The only telaro event that carries its own ARS job id.
      const jobId = hex(payload.data.actionHash);
      return {
        type: "EvidenceSubmitted",
        jobId,
        at: ctx.at,
        actionHash: jobId,
        // telaro outcome: 0 success, 1 failed, 2 disputed.
        outcome: payload.data.outcome === 0 ? "success" : "failed",
      };
    }

    case "ClaimSubmitted": {
      if (!ctx.jobId) return null;
      return {
        type: "Disputed",
        jobId: ctx.jobId,
        at: ctx.at,
        claim: payload.data.claim.toBase58(),
      };
    }

    case "ClaimResolved": {
      if (!ctx.jobId) return null;
      return {
        type: "Closed",
        jobId: ctx.jobId,
        at: ctx.at,
        resolution: claimStatusResolution(payload.data.status),
      };
    }

    case "ArbiterRuled": {
      if (!ctx.jobId) return null;
      return {
        type: "Closed",
        jobId: ctx.jobId,
        at: ctx.at,
        // ruling: 0 ForUser, 1 ForBuilder, 2 ForUserTimeout.
        resolution:
          payload.data.ruling === 1 ? "dispute_rejected" : "dispute_upheld",
      };
    }

    case "CreditDrawn": {
      if (!ctx.jobId) return null;
      return {
        type: "PrincipalReleased",
        jobId: ctx.jobId,
        at: ctx.at,
        amountAtomic: payload.data.amount,
      };
    }

    default:
      // No principal-track analogue.
      return null;
  }
}
