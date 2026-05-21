/**
 * The ARS `SettlementLayer` contract, expressed for Telaro on Solana.
 *
 * The reconcile against `programs/telaro` (dual-track redesign §3) found
 * that 6 of the 8 ARS settlement methods already map onto telaro program
 * instructions that exist on-chain. The two `*Fee` methods are out of
 * scope for v1 — Telaro is a capital-risk layer, not a generic
 * service-fee escrow (§4.2).
 *
 * This file pins the contract: the `SettlementLayer` interface and the
 * `TELARO_SETTLEMENT_MAP`. `binding.ts` builds the instructions;
 * `client.ts` (`TelaroSettlement`) implements this interface by sending
 * them.
 */

import type { Keypair } from "@solana/web3.js";
import type {
  LockCollateralParams,
  SlashCollateralParams,
  UnlockCollateralParams,
  PayPremiumParams,
  ReleasePrincipalParams,
} from "./binding.js";

/** Result of a settlement action that touched the chain. */
export interface SettleResult {
  jobId: string;
  /** Solana transaction signature. */
  signature: string;
}

/** How an ARS settlement method is realised on the telaro program. */
export interface TelaroBinding {
  /** telaro program instruction(s) that back this method. */
  instruction: string;
  note: string;
}

/**
 * ARS `SettlementLayer` method → telaro instruction. The single source of
 * truth for the on-chain binding.
 */
export const TELARO_SETTLEMENT_MAP = {
  lockCollateral: {
    instruction: "view_bond",
    note: "standing bond + Agent.reserved_for_claims exposure accounting; leverage must stay <= MAX_LEVERAGE_RATIO (5x)",
  },
  slashCollateral: {
    instruction: "resolve_claim / arbiter_resolve",
    note: "a ForUser ruling pays the harmed party out of the agent's bond",
  },
  unlockCollateral: {
    instruction: "withdraw_bond",
    note: "released once the job closes, subject to the 30d withdrawal cooldown",
  },
  payPremium: {
    instruction: "process_pool_yield / fund_insurance",
    note: "premium routes to the UnderwriterPool (decentralised) or the InsuranceVault backstop",
  },
  releasePrincipal: {
    instruction: "request_credit",
    note: "under-collateralised draw from the UnderwriterPool; agent score must be >= 700",
  },
  lockFee: {
    instruction: "(none)",
    note: "fee track is out of scope for v1 — see dual-track redesign 4.2",
  },
  releaseFee: {
    instruction: "(none)",
    note: "fee track is out of scope for v1 — see dual-track redesign 4.2",
  },
  refundFee: {
    instruction: "(none)",
    note: "fee track is out of scope for v1 — see dual-track redesign 4.2",
  },
} as const satisfies Record<string, TelaroBinding>;

export type SettlementMethod = keyof typeof TELARO_SETTLEMENT_MAP;

/**
 * The principal-track settlement surface Telaro implements. Each method
 * builds the mapped telaro instruction (`binding.ts`) and sends it;
 * `signers` must list every required signer, fee payer first. The `*Fee`
 * methods are omitted deliberately (out of scope for v1).
 *
 * Implemented by `TelaroSettlement` in `client.ts`.
 */
export interface SettlementLayer {
  lockCollateral(
    params: LockCollateralParams,
    signers: Keypair[]
  ): Promise<SettleResult>;
  slashCollateral(
    params: SlashCollateralParams,
    signers: Keypair[]
  ): Promise<SettleResult>;
  unlockCollateral(
    params: UnlockCollateralParams,
    signers: Keypair[]
  ): Promise<SettleResult>;
  payPremium(
    params: PayPremiumParams,
    signers: Keypair[]
  ): Promise<SettleResult>;
  releasePrincipal(
    params: ReleasePrincipalParams,
    signers: Keypair[]
  ): Promise<SettleResult>;
}
