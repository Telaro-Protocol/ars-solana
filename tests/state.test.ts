import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { applyEvent, replay, isTerminal, ARSTransitionError } from "../src/index.js";
import type { ArsEvent } from "../src/index.js";

const JOB = "actionhash-job-1";
const AGENT = "Agent1111111111111111111111111111111111111111";
const REQ = "Dapp11111111111111111111111111111111111111111";

let clock = 1_700_000_000;
const tick = () => ++clock;

const opened = (): ArsEvent => ({
  type: "JobOpened",
  jobId: JOB,
  at: tick(),
  agent: AGENT,
  requestor: REQ,
  exposureAtomic: 5_000_000_000n,
});
const uwStart = (): ArsEvent => ({ type: "UnderwritingStarted", jobId: JOB, at: tick() });
const uwDecided = (passed: boolean, failureCode?: string): ArsEvent => ({
  type: "UnderwritingDecided",
  jobId: JOB,
  at: tick(),
  passed,
  failureCode,
});
const released = (amountAtomic: bigint): ArsEvent => ({
  type: "PrincipalReleased",
  jobId: JOB,
  at: tick(),
  amountAtomic,
});
const evidence = (outcome: "success" | "failed"): ArsEvent => ({
  type: "EvidenceSubmitted",
  jobId: JOB,
  at: tick(),
  actionHash: JOB,
  outcome,
});
const disputed = (): ArsEvent => ({ type: "Disputed", jobId: JOB, at: tick(), claim: "Claim111" });
const closed = (resolution: "no_dispute" | "dispute_upheld" | "dispute_rejected"): ArsEvent => ({
  type: "Closed",
  jobId: JOB,
  at: tick(),
  resolution,
});

/* ------------------------------------------------------------------ */

describe("principal-track lifecycle — happy paths", () => {
  it("runs the full clean lifecycle to CLOSED", () => {
    const job = replay([
      opened(),
      uwStart(),
      uwDecided(true),
      released(2_000_000_000n),
      evidence("success"),
      closed("no_dispute"),
    ]);
    assert.equal(job.state, "CLOSED");
    assert.equal(job.releasedAtomic, 2_000_000_000n);
    assert.equal(isTerminal(job.state), true);
  });

  it("ends in REJECTED when underwriting fails", () => {
    const job = replay([opened(), uwStart(), uwDecided(false, "NOT_BONDED")]);
    assert.equal(job.state, "REJECTED");
    assert.equal(isTerminal(job.state), true);
    assert.equal(job.releasedAtomic, 0n);
  });

  it("runs the dispute path to CLOSED", () => {
    const job = replay([
      opened(),
      uwStart(),
      uwDecided(true),
      released(1_000_000_000n),
      evidence("failed"),
      disputed(),
      closed("dispute_upheld"),
    ]);
    assert.equal(job.state, "CLOSED");
  });

  it("accumulates principal across multiple releases", () => {
    const job = replay([
      opened(),
      uwStart(),
      uwDecided(true),
      released(1_000_000_000n),
      released(500_000_000n),
      released(250_000_000n),
    ]);
    assert.equal(job.state, "EXECUTING");
    assert.equal(job.releasedAtomic, 1_750_000_000n);
  });
});

describe("principal-track lifecycle — illegal transitions throw", () => {
  const throws = (events: ArsEvent[]) =>
    assert.throws(() => replay(events), (e: unknown) => e instanceof ARSTransitionError);

  it("rejects PrincipalReleased before underwriting passes", () => {
    throws([opened(), uwStart(), released(1n)]);
  });

  it("rejects releasing principal on a rejected job", () => {
    throws([opened(), uwStart(), uwDecided(false), released(1n)]);
  });

  it("rejects a second JobOpened", () => {
    throws([opened(), opened()]);
  });

  it("rejects an event for an unopened job", () => {
    throws([uwStart()]);
  });

  it("rejects any event after a terminal state", () => {
    throws([opened(), uwStart(), uwDecided(true), released(1n), evidence("success"), closed("no_dispute"), uwStart()]);
  });

  it("rejects a dispute before evidence is submitted", () => {
    throws([opened(), uwStart(), uwDecided(true), released(1n), disputed()]);
  });

  it("rejects closing a job that never reached evidence", () => {
    throws([opened(), uwStart(), uwDecided(true), closed("no_dispute")]);
  });

  it("rejects replaying an empty log", () => {
    throws([]);
  });

  it("rejects an event whose jobId does not match the job", () => {
    assert.throws(
      () =>
        applyEvent(
          { jobId: JOB, agent: AGENT, requestor: REQ, exposureAtomic: 1n, state: "AWAIT_UNDERWRITING", releasedAtomic: 0n, lastEventAt: 0 },
          { type: "UnderwritingStarted", jobId: "other-job", at: 1 }
        ),
      (e: unknown) => e instanceof ARSTransitionError
    );
  });
});
