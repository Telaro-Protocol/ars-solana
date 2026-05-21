/**
 * Async settlement client — sends ARS principal-track settlement
 * instructions to the telaro program.
 *
 * `binding.ts` builds the instructions (pure); `TelaroSettlement` wraps
 * them with transaction send. Sending is abstracted behind `TxSender` so
 * the same client runs against a live RPC (`connectionSender`) or an
 * in-process bankrun runtime — which is how the binding instructions are
 * verified end to end against the real `telaro.so`.
 */

import {
  Connection,
  type Keypair,
  type PublicKey,
  Transaction,
  type TransactionInstruction,
  sendAndConfirmTransaction,
} from "@solana/web3.js";
import { PROGRAM_ID } from "@telaro/sdk";
import {
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
import type { SettlementLayer, SettleResult } from "./settlement.js";

/**
 * Sends one transaction's worth of instructions and returns the
 * signature. The first signer is the fee payer. Abstracted so the
 * settlement client is not bound to a live RPC — tests inject a
 * bankrun-backed sender.
 */
export interface TxSender {
  send(
    instructions: TransactionInstruction[],
    signers: Keypair[]
  ): Promise<string>;
}

/** A {@link TxSender} backed by a web3.js `Connection`. */
export function connectionSender(connection: Connection): TxSender {
  return {
    async send(instructions, signers) {
      if (signers.length === 0) {
        throw new Error(
          "connectionSender: at least one signer (the fee payer) is required"
        );
      }
      const tx = new Transaction().add(...instructions);
      tx.feePayer = signers[0].publicKey;
      const { blockhash } = await connection.getLatestBlockhash();
      tx.recentBlockhash = blockhash;
      return sendAndConfirmTransaction(connection, tx, signers);
    },
  };
}

/**
 * The ARS `SettlementLayer` for Telaro on Solana. Each method builds the
 * mapped telaro instruction (`binding.ts`) and sends it via the
 * configured {@link TxSender}.
 *
 * `signers` must list every required signer with the fee payer first —
 * e.g. `releasePrincipal` needs the agent's controller, `payPremium`
 * needs the premium source authority.
 */
export class TelaroSettlement implements SettlementLayer {
  private readonly sender: TxSender;
  private readonly programId: PublicKey;

  constructor(opts: { sender: TxSender; programId?: PublicKey }) {
    this.sender = opts.sender;
    this.programId = opts.programId ?? PROGRAM_ID;
  }

  lockCollateral(
    params: LockCollateralParams,
    signers: Keypair[]
  ): Promise<SettleResult> {
    return this.run(params.jobId, lockCollateralIx(params, this.programId), signers);
  }

  slashCollateral(
    params: SlashCollateralParams,
    signers: Keypair[]
  ): Promise<SettleResult> {
    return this.run(params.jobId, slashCollateralIx(params, this.programId), signers);
  }

  unlockCollateral(
    params: UnlockCollateralParams,
    signers: Keypair[]
  ): Promise<SettleResult> {
    return this.run(params.jobId, unlockCollateralIx(params, this.programId), signers);
  }

  payPremium(
    params: PayPremiumParams,
    signers: Keypair[]
  ): Promise<SettleResult> {
    return this.run(params.jobId, payPremiumIx(params, this.programId), signers);
  }

  releasePrincipal(
    params: ReleasePrincipalParams,
    signers: Keypair[]
  ): Promise<SettleResult> {
    return this.run(params.jobId, releasePrincipalIx(params, this.programId), signers);
  }

  private async run(
    jobId: string,
    instruction: TransactionInstruction,
    signers: Keypair[]
  ): Promise<SettleResult> {
    const signature = await this.sender.send([instruction], signers);
    return { jobId, signature };
  }
}
