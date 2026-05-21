import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { Keypair } from "@solana/web3.js";
import type { DecodedEventPayload } from "@telaro/sdk";
import { toArsEvent } from "../src/index.js";

const AT = 1_700_000_500;
const key = () => Keypair.generate().publicKey;
const actionHash = Uint8Array.from({ length: 32 }, (_, i) => i + 1);
const hashHex = Buffer.from(actionHash).toString("hex");

describe("toArsEvent — telaro event → ARS event", () => {
  it("maps ActionRecorded to EvidenceSubmitted (job id from the action hash)", () => {
    const payload: DecodedEventPayload = {
      name: "ActionRecorded",
      data: { agent: key(), actionHash, kind: 0, outcome: 0, valueAtomic: 1n, slot: 9n },
    };
    const e = toArsEvent(payload, { at: AT });
    assert.equal(e?.type, "EvidenceSubmitted");
    assert.equal(e?.jobId, hashHex);
    assert.equal(e?.type === "EvidenceSubmitted" && e.outcome, "success");
  });

  it("maps a failed action outcome to outcome 'failed'", () => {
    const payload: DecodedEventPayload = {
      name: "ActionRecorded",
      data: { agent: key(), actionHash, kind: 0, outcome: 1, valueAtomic: 1n, slot: 9n },
    };
    const e = toArsEvent(payload, { at: AT });
    assert.equal(e?.type === "EvidenceSubmitted" && e.outcome, "failed");
  });

  it("maps ClaimSubmitted to Disputed when ctx.jobId is supplied", () => {
    const claim = key();
    const payload: DecodedEventPayload = {
      name: "ClaimSubmitted",
      data: { claim, agent: key(), claimer: key(), claimedAmount: 100n, deadline: 0n, isFastTrack: false },
    };
    const e = toArsEvent(payload, { at: AT, jobId: hashHex });
    assert.equal(e?.type, "Disputed");
    assert.equal(e?.type === "Disputed" && e.claim, claim.toBase58());
  });

  it("returns null for a claim event without ctx.jobId (action hash not in payload)", () => {
    const payload: DecodedEventPayload = {
      name: "ClaimSubmitted",
      data: { claim: key(), agent: key(), claimer: key(), claimedAmount: 100n, deadline: 0n, isFastTrack: false },
    };
    assert.equal(toArsEvent(payload, { at: AT }), null);
  });

  it("maps ClaimResolved status to a Closed resolution", () => {
    const upheld: DecodedEventPayload = {
      name: "ClaimResolved",
      data: { claim: key(), agent: key(), status: 1, paidOut: 100n }, // AcceptedByBuilder
    };
    const rejected: DecodedEventPayload = {
      name: "ClaimResolved",
      data: { claim: key(), agent: key(), status: 3, paidOut: 0n }, // RejectedByBuilder
    };
    assert.equal(
      (toArsEvent(upheld, { at: AT, jobId: hashHex }) as { resolution: string }).resolution,
      "dispute_upheld"
    );
    assert.equal(
      (toArsEvent(rejected, { at: AT, jobId: hashHex }) as { resolution: string }).resolution,
      "dispute_rejected"
    );
  });

  it("maps ArbiterRuled ForBuilder to dispute_rejected, ForUser to dispute_upheld", () => {
    const mk = (ruling: number): DecodedEventPayload => ({
      name: "ArbiterRuled",
      data: {
        claim: key(),
        agent: key(),
        arbiter: key(),
        ruling,
        bondPaidToUser: 0n,
        treasuryReceived: 0n,
        arbiterFeeReceived: 0n,
        rulingTimeSeconds: 0n,
      },
    });
    assert.equal((toArsEvent(mk(1), { at: AT, jobId: hashHex }) as { resolution: string }).resolution, "dispute_rejected");
    assert.equal((toArsEvent(mk(0), { at: AT, jobId: hashHex }) as { resolution: string }).resolution, "dispute_upheld");
  });

  it("maps CreditDrawn to PrincipalReleased with ctx.jobId", () => {
    const payload: DecodedEventPayload = {
      name: "CreditDrawn",
      data: {
        agent: key(),
        creditLine: key(),
        amount: 250_000_000n,
        interestRateBps: 800,
        outstandingPrincipal: 250_000_000n,
        accruedInterest: 0n,
        scoreAtDraw: 800,
      },
    };
    const e = toArsEvent(payload, { at: AT, jobId: hashHex });
    assert.equal(e?.type, "PrincipalReleased");
    assert.equal(e?.type === "PrincipalReleased" && e.amountAtomic, 250_000_000n);
  });

  it("returns null for telaro events with no principal-track analogue", () => {
    const payload: DecodedEventPayload = {
      name: "BondTopUp",
      data: { agent: key(), by: key(), amount: 1n, newBond: 2n },
    };
    assert.equal(toArsEvent(payload, { at: AT }), null);
  });
});
