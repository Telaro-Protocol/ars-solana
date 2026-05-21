import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { InMemoryEventStore, ARSTransitionError } from "../src/index.js";
import type { ArsEvent } from "../src/index.js";

const AGENT = "Agent1111111111111111111111111111111111111111";
const REQ = "Dapp11111111111111111111111111111111111111111";

let clock = 1_700_000_000;
const at = () => ++clock;

const opened = (jobId: string): ArsEvent => ({
  type: "JobOpened",
  jobId,
  at: at(),
  agent: AGENT,
  requestor: REQ,
  exposureAtomic: 5_000_000_000n,
});
const uwStart = (jobId: string): ArsEvent => ({ type: "UnderwritingStarted", jobId, at: at() });
const uwDecided = (jobId: string, passed: boolean): ArsEvent => ({
  type: "UnderwritingDecided",
  jobId,
  at: at(),
  passed,
});

describe("InMemoryEventStore", () => {
  it("derives the current job from the appended log", async () => {
    const store = new InMemoryEventStore();
    await store.append(opened("job-1"));
    await store.append(uwStart("job-1"));
    await store.append(uwDecided("job-1", true));

    const job = await store.job("job-1");
    assert.equal(job?.state, "RELEASABLE");
    assert.equal((await store.log("job-1")).length, 3);
  });

  it("returns null for an unknown job and [] for its log", async () => {
    const store = new InMemoryEventStore();
    assert.equal(await store.job("nope"), null);
    assert.deepEqual(await store.log("nope"), []);
  });

  it("rejects an illegal transition and leaves the log untouched", async () => {
    const store = new InMemoryEventStore();
    await store.append(opened("job-1"));
    await assert.rejects(
      store.append(uwDecided("job-1", true)), // no UnderwritingStarted yet
      (e: unknown) => e instanceof ARSTransitionError
    );
    assert.equal((await store.log("job-1")).length, 1);
  });

  it("rejects a non-opening event for an unknown job", async () => {
    const store = new InMemoryEventStore();
    await assert.rejects(
      store.append(uwStart("ghost")),
      (e: unknown) => e instanceof ARSTransitionError
    );
  });

  it("keeps separate jobs independent", async () => {
    const store = new InMemoryEventStore();
    await store.append(opened("job-a"));
    await store.append(opened("job-b"));
    await store.append(uwStart("job-a"));

    assert.equal((await store.job("job-a"))?.state, "UNDERWRITING");
    assert.equal((await store.job("job-b"))?.state, "AWAIT_UNDERWRITING");
    assert.deepEqual((await store.jobIds()).sort(), ["job-a", "job-b"]);
  });

  it("returns a copy of the log — callers cannot mutate stored state", async () => {
    const store = new InMemoryEventStore();
    await store.append(opened("job-1"));
    const log = await store.log("job-1");
    log.push(uwStart("job-1"));
    assert.equal((await store.log("job-1")).length, 1);
  });
});
