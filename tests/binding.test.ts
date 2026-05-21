import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { Keypair } from "@solana/web3.js";
import { PROGRAM_ID, INSTRUCTION_DISC } from "@telaro/sdk";
import {
  lockCollateralIx,
  slashCollateralIx,
  unlockCollateralIx,
  payPremiumIx,
  releasePrincipalIx,
} from "../src/index.js";

const key = () => Keypair.generate().publicKey;
const JOB = "actionhash-job-1";

/** Every binding instruction must target the telaro program and lead
 *  with the matching Anchor discriminator. */
function assertIx(
  ix: { programId: { equals(o: unknown): boolean }; data: Buffer; keys: unknown[] },
  disc: Buffer,
  expectedKeys: number,
) {
  assert.equal(ix.programId.equals(PROGRAM_ID), true, "programId is the telaro program");
  assert.equal(
    Buffer.from(ix.data.subarray(0, 8)).equals(disc),
    true,
    "instruction data leads with the expected discriminator",
  );
  assert.equal(ix.keys.length, expectedKeys, `expected ${expectedKeys} account keys`);
}

describe("ARS settlement → telaro instruction binding", () => {
  it("lockCollateral builds a view_bond instruction", () => {
    const ix = lockCollateralIx({
      jobId: JOB,
      agent: key(),
      minBondAtomic: 1_000_000_000n,
      minScore: 700,
    });
    assertIx(ix, INSTRUCTION_DISC.viewBond, 1);
  });

  it("slashCollateral builds a resolve_claim instruction", () => {
    const ix = slashCollateralIx({
      jobId: JOB,
      claim: key(),
      agent: key(),
      bondMint: key(),
      claimerBondAta: key(),
      signer: key(),
    });
    assertIx(ix, INSTRUCTION_DISC.resolveClaim, 8);
    // action byte 0 = builder accepts → bond pays the claimer.
    assert.equal(ix.data[8], 0);
  });

  it("unlockCollateral builds a withdraw_bond instruction", () => {
    const ix = unlockCollateralIx({
      jobId: JOB,
      agent: key(),
      bondMint: key(),
      controller: key(),
      controllerBondAta: key(),
      amountAtomic: 2_000_000_000n,
    });
    assertIx(ix, INSTRUCTION_DISC.withdrawBond, 6);
  });

  it("payPremium builds a process_pool_yield instruction", () => {
    const ix = payPremiumIx({
      jobId: JOB,
      sourceAta: key(),
      sourceAuthority: key(),
      amountAtomic: 50_000_000n,
    });
    assertIx(ix, INSTRUCTION_DISC.processPoolYield, 5);
  });

  it("releasePrincipal builds a request_credit instruction", () => {
    const ix = releasePrincipalIx({
      jobId: JOB,
      agent: key(),
      controller: key(),
      amountAtomic: 3_000_000_000n,
    });
    assertIx(ix, INSTRUCTION_DISC.requestCredit, 9);
  });
});
