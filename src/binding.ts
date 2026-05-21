/**
 * On-chain binding — ARS principal-track settlement → telaro instructions.
 *
 * Each function turns one ARS settlement action into a Solana
 * `TransactionInstruction` for the `telaro` program, built via
 * `@telaro/sdk`. Mapping rationale: `settlement.ts` (`TELARO_SETTLEMENT_MAP`)
 * and docs/internal/ars-dual-track-redesign.md §3.
 *
 * Scope: this is the **instruction layer** — pure, no network. Assembling
 * a `Transaction`, attaching signers and sending it is the caller's job
 * (standard Solana) and is intentionally left out so this layer stays
 * verifiable without a validator. A full async `SettlementLayer`
 * (settlement.ts) that wraps these with a `Connection` is the next step.
 *
 * Fee-track methods (`lockFee`/`releaseFee`/`refundFee`) are not here —
 * out of scope for v1 (dual-track redesign §4.2).
 */

import type { PublicKey, TransactionInstruction } from "@solana/web3.js";
import {
  PROGRAM_ID,
  buildViewBondIx,
  buildResolveClaimIx,
  buildWithdrawBondIx,
  buildProcessPoolYieldIx,
  buildRequestCreditIx,
} from "@telaro/sdk";

/**
 * `lockCollateral` — assert the agent's standing bond covers the job.
 *
 * Telaro has no per-job collateral transfer: the standing bond backs all
 * of an agent's jobs and the 5x leverage cap (checked inside `view_bond`)
 * governs aggregate exposure. So "locking collateral" for a job is the
 * underwriting assertion — `view_bond` reverts if the agent fails policy.
 */
export interface LockCollateralParams {
  jobId: string;
  agent: PublicKey;
  /** Minimum bond the agent must hold (USDC atomic, 6dp). */
  minBondAtomic: bigint;
  /** Minimum score, 0–1000. */
  minScore: number;
}

export function lockCollateralIx(
  params: LockCollateralParams,
  programId: PublicKey = PROGRAM_ID
): TransactionInstruction {
  return buildViewBondIx(
    params.agent,
    { minBond: params.minBondAtomic, minScore: params.minScore },
    programId
  );
}

/**
 * `slashCollateral` — pay a harmed party out of the agent's bond.
 *
 * Maps to `resolve_claim` with action `0` (builder accepts the claim):
 * the bond pays `claimedAmount` to the claimer.
 */
export interface SlashCollateralParams {
  jobId: string;
  /** The `Claim` PDA being resolved. */
  claim: PublicKey;
  agent: PublicKey;
  bondMint: PublicKey;
  /** The harmed party's bond-mint ATA — receives the slashed funds. */
  claimerBondAta: PublicKey;
  /** The agent's controller, signing the accept. */
  signer: PublicKey;
}

/** `resolve_claim` action: 0 = builder accepts the claim. */
const RESOLVE_ACCEPT = 0;

export function slashCollateralIx(
  params: SlashCollateralParams,
  programId: PublicKey = PROGRAM_ID
): TransactionInstruction {
  return buildResolveClaimIx(
    {
      claim: params.claim,
      agent: params.agent,
      bondMint: params.bondMint,
      claimerBondAta: params.claimerBondAta,
      signer: params.signer,
    },
    RESOLVE_ACCEPT,
    programId
  );
}

/**
 * `unlockCollateral` — return bond to the agent once the job closes.
 * Maps to `withdraw_bond` (subject to the 30d withdrawal cooldown).
 */
export interface UnlockCollateralParams {
  jobId: string;
  agent: PublicKey;
  bondMint: PublicKey;
  controller: PublicKey;
  /** The controller's bond-mint ATA — receives the returned bond. */
  controllerBondAta: PublicKey;
  amountAtomic: bigint;
}

export function unlockCollateralIx(
  params: UnlockCollateralParams,
  programId: PublicKey = PROGRAM_ID
): TransactionInstruction {
  return buildWithdrawBondIx(
    {
      agent: params.agent,
      bondMint: params.bondMint,
      controller: params.controller,
      controllerBondAta: params.controllerBondAta,
    },
    params.amountAtomic,
    programId
  );
}

/**
 * `payPremium` — route a premium into the decentralised underwriter pool.
 * Maps to `process_pool_yield` (arbiter fees / premiums → `UnderwriterPool`).
 */
export interface PayPremiumParams {
  jobId: string;
  /** Token account the premium is paid from. */
  sourceAta: PublicKey;
  /** Authority that signs the premium transfer. */
  sourceAuthority: PublicKey;
  amountAtomic: bigint;
}

export function payPremiumIx(
  params: PayPremiumParams,
  programId: PublicKey = PROGRAM_ID
): TransactionInstruction {
  return buildProcessPoolYieldIx(
    { sourceAta: params.sourceAta, sourceAuthority: params.sourceAuthority },
    params.amountAtomic,
    programId
  );
}

/**
 * `releasePrincipal` — release principal (credit) to the agent.
 * Maps to `request_credit`: an under-collateralised draw from the
 * `UnderwriterPool`. The program enforces score ≥ 700.
 */
export interface ReleasePrincipalParams {
  jobId: string;
  agent: PublicKey;
  controller: PublicKey;
  amountAtomic: bigint;
}

export function releasePrincipalIx(
  params: ReleasePrincipalParams,
  programId: PublicKey = PROGRAM_ID
): TransactionInstruction {
  return buildRequestCreditIx(
    { agent: params.agent, controller: params.controller },
    params.amountAtomic,
    programId
  );
}
