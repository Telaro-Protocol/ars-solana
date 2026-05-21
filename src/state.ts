/**
 * ARS principal-track state machine.
 *
 * A `Job`'s lifecycle state is *derived* — `replay()` folds an event log
 * (see `events.ts`) into the current `Job`. `applyEvent()` is the single
 * transition function; an illegal transition throws `ARSTransitionError`
 * rather than silently producing a bad state.
 *
 * This is the explicit pre-execution lifecycle that the telaro program
 * left implicit (`view_bond` is a stateless CPI check) — the genuinely
 * new piece of the ARS-Solana implementation
 * (docs/internal/ars-dual-track-redesign.md §4.1, §6).
 */

import type { ArsEvent } from "./events.js";

/**
 * Principal-track lifecycle states.
 *
 *  AWAIT_UNDERWRITING → UNDERWRITING → RELEASABLE → EXECUTING
 *    → EVIDENCE_SUBMITTED → (DISPUTED →) CLOSED
 *  UNDERWRITING → REJECTED
 */
export type PrincipalState =
  | "AWAIT_UNDERWRITING"
  | "UNDERWRITING"
  | "REJECTED"
  | "RELEASABLE"
  | "EXECUTING"
  | "EVIDENCE_SUBMITTED"
  | "DISPUTED"
  | "CLOSED";

const TERMINAL: ReadonlySet<PrincipalState> = new Set<PrincipalState>([
  "REJECTED",
  "CLOSED",
]);

/** A job in a terminal state accepts no further events. */
export function isTerminal(state: PrincipalState): boolean {
  return TERMINAL.has(state);
}

export interface Job {
  jobId: string;
  /** Agent wallet — the Telaro agent key. */
  agent: string;
  /** DApp / capital provider that opened the job. */
  requestor: string;
  /** Capital the agent handles for this job (USDC atomic, 6dp). */
  exposureAtomic: bigint;
  state: PrincipalState;
  /** Principal released to the agent so far (atomic). */
  releasedAtomic: bigint;
  /** `at` of the most recently applied event. */
  lastEventAt: number;
}

export class ARSTransitionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ARSTransitionError";
  }
}

/**
 * Apply one event to a job, returning the next job. Pass `null` as `job`
 * only for the opening `JobOpened` event. Throws `ARSTransitionError` for
 * any illegal transition.
 */
export function applyEvent(job: Job | null, event: ArsEvent): Job {
  if (event.type === "JobOpened") {
    if (job) {
      throw new ARSTransitionError(
        `JobOpened for ${event.jobId}: job already exists`
      );
    }
    return {
      jobId: event.jobId,
      agent: event.agent,
      requestor: event.requestor,
      exposureAtomic: event.exposureAtomic,
      state: "AWAIT_UNDERWRITING",
      releasedAtomic: 0n,
      lastEventAt: event.at,
    };
  }

  if (!job) {
    throw new ARSTransitionError(
      `${event.type} for unknown job ${event.jobId}`
    );
  }
  if (job.jobId !== event.jobId) {
    throw new ARSTransitionError(
      `event jobId ${event.jobId} does not match job ${job.jobId}`
    );
  }
  if (isTerminal(job.state)) {
    throw new ARSTransitionError(
      `${event.type}: job ${job.jobId} is terminal (${job.state})`
    );
  }

  const j = job;
  const to = (state: PrincipalState, patch?: Partial<Job>): Job => ({
    ...j,
    ...patch,
    state,
    lastEventAt: event.at,
  });
  const illegal = (): never => {
    throw new ARSTransitionError(
      `${event.type} is not allowed in state ${j.state}`
    );
  };

  switch (event.type) {
    case "UnderwritingStarted":
      return j.state === "AWAIT_UNDERWRITING" ? to("UNDERWRITING") : illegal();

    case "UnderwritingDecided":
      if (j.state !== "UNDERWRITING") return illegal();
      return to(event.passed ? "RELEASABLE" : "REJECTED");

    case "PrincipalReleased":
      // Principal can be drawn more than once (the credit line supports
      // repeated `request_credit` calls), so EXECUTING accepts it too.
      if (j.state !== "RELEASABLE" && j.state !== "EXECUTING") return illegal();
      return to("EXECUTING", {
        releasedAtomic: j.releasedAtomic + event.amountAtomic,
      });

    case "EvidenceSubmitted":
      return j.state === "EXECUTING" ? to("EVIDENCE_SUBMITTED") : illegal();

    case "Disputed":
      return j.state === "EVIDENCE_SUBMITTED" ? to("DISPUTED") : illegal();

    case "Closed":
      return j.state === "EVIDENCE_SUBMITTED" || j.state === "DISPUTED"
        ? to("CLOSED")
        : illegal();
  }
}

/** Derive the current job by replaying its full event log. */
export function replay(events: readonly ArsEvent[]): Job {
  let job: Job | null = null;
  for (const event of events) {
    job = applyEvent(job, event);
  }
  if (!job) {
    throw new ARSTransitionError("cannot replay an empty event log");
  }
  return job;
}
