import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import { Keypair, type TransactionInstruction } from "@solana/web3.js";
import { PROGRAM_ID, INSTRUCTION_DISC } from "@telaro/sdk";
import { TelaroSettlement, type TxSender } from "../src/index.js";

/** A TxSender that records calls instead of sending — verifies the
 *  client builds the right instruction and threads jobId/signers. */
function recordingSender() {
  const calls: { instructions: TransactionInstruction[]; signers: Keypair[] }[] = [];
  let n = 0;
  const sender: TxSender = {
    async send(instructions, signers) {
      calls.push({ instructions, signers });
      return `mock-sig-${++n}`;
    },
  };
  return { sender, calls };
}

const key = () => Keypair.generate().publicKey;

function leadsWith(ix: TransactionInstruction, disc: Buffer): boolean {
  return Buffer.from(ix.data.subarray(0, 8)).equals(disc);
}

describe("TelaroSettlement — async settlement client", () => {
  it("lockCollateral sends view_bond and returns the signature", async () => {
    const { sender, calls } = recordingSender();
    const s = new TelaroSettlement({ sender });
    const feePayer = Keypair.generate();

    const res = await s.lockCollateral(
      { jobId: "job-1", agent: key(), minBondAtomic: 1_000_000_000n, minScore: 700 },
      [feePayer]
    );

    assert.equal(res.jobId, "job-1");
    assert.equal(res.signature, "mock-sig-1");
    assert.equal(calls.length, 1);
    const ix = calls[0].instructions[0];
    assert.equal(ix.programId.equals(PROGRAM_ID), true);
    assert.equal(leadsWith(ix, INSTRUCTION_DISC.viewBond), true);
    assert.deepEqual(calls[0].signers, [feePayer]);
  });

  it("slashCollateral sends resolve_claim", async () => {
    const { sender, calls } = recordingSender();
    const s = new TelaroSettlement({ sender });
    const res = await s.slashCollateral(
      {
        jobId: "job-2",
        claim: key(),
        agent: key(),
        bondMint: key(),
        claimerBondAta: key(),
        signer: key(),
      },
      [Keypair.generate()]
    );
    assert.equal(res.jobId, "job-2");
    assert.equal(leadsWith(calls[0].instructions[0], INSTRUCTION_DISC.resolveClaim), true);
  });

  it("unlockCollateral sends withdraw_bond", async () => {
    const { sender, calls } = recordingSender();
    const s = new TelaroSettlement({ sender });
    await s.unlockCollateral(
      {
        jobId: "job-3",
        agent: key(),
        bondMint: key(),
        controller: key(),
        controllerBondAta: key(),
        amountAtomic: 500_000_000n,
      },
      [Keypair.generate()]
    );
    assert.equal(leadsWith(calls[0].instructions[0], INSTRUCTION_DISC.withdrawBond), true);
  });

  it("payPremium sends process_pool_yield", async () => {
    const { sender, calls } = recordingSender();
    const s = new TelaroSettlement({ sender });
    await s.payPremium(
      { jobId: "job-4", sourceAta: key(), sourceAuthority: key(), amountAtomic: 50_000_000n },
      [Keypair.generate()]
    );
    assert.equal(leadsWith(calls[0].instructions[0], INSTRUCTION_DISC.processPoolYield), true);
  });

  it("releasePrincipal sends request_credit", async () => {
    const { sender, calls } = recordingSender();
    const s = new TelaroSettlement({ sender });
    const res = await s.releasePrincipal(
      { jobId: "job-5", agent: key(), controller: key(), amountAtomic: 3_000_000_000n },
      [Keypair.generate()]
    );
    assert.equal(res.signature, "mock-sig-1");
    assert.equal(leadsWith(calls[0].instructions[0], INSTRUCTION_DISC.requestCredit), true);
  });
});
