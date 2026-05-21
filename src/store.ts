/**
 * ARS event store.
 *
 * `state.ts` derives a job by replaying its event log; the store is where
 * that log lives. It is append-only and **validates on append** — an
 * event that is not a legal transition for the job's current state is
 * rejected before it is persisted, so a stored log always replays into a
 * valid job.
 *
 * The interface is async so a durable backend (the ARS reference uses a
 * signed SQLite log) can drop in without an interface change. v1 ships
 * the in-memory implementation.
 */

import type { ArsEvent } from "./events.js";
import { applyEvent, replay, type Job } from "./state.js";

export interface EventStore {
  /**
   * Append one event. Throws `ARSTransitionError` if it is not a legal
   * transition for the job's current state — the log is left untouched.
   */
  append(event: ArsEvent): Promise<void>;

  /** The ordered event log for a job (empty array if the job is unknown). */
  log(jobId: string): Promise<ArsEvent[]>;

  /** The current derived job, or `null` if it has no events. */
  job(jobId: string): Promise<Job | null>;

  /** Every job id the store has seen. */
  jobIds(): Promise<string[]>;
}

/**
 * In-memory {@link EventStore} — a `Map` of per-job event logs. The
 * default store; suitable for a single process, tests, or a cache in
 * front of a durable store.
 */
export class InMemoryEventStore implements EventStore {
  private readonly logs = new Map<string, ArsEvent[]>();

  async append(event: ArsEvent): Promise<void> {
    const existing = this.logs.get(event.jobId) ?? [];
    const current = existing.length > 0 ? replay(existing) : null;
    // Validate: throws ARSTransitionError on an illegal transition, so an
    // invalid event never reaches the persisted log.
    applyEvent(current, event);
    this.logs.set(event.jobId, [...existing, event]);
  }

  async log(jobId: string): Promise<ArsEvent[]> {
    return [...(this.logs.get(jobId) ?? [])];
  }

  async job(jobId: string): Promise<Job | null> {
    const events = this.logs.get(jobId);
    return events && events.length > 0 ? replay(events) : null;
  }

  async jobIds(): Promise<string[]> {
    return [...this.logs.keys()];
  }
}
