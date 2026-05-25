# telaro-ars

**Python adapter for the [ARS-Solana Profile](../SPEC.md).** Implements
the [Agentic Risk Standard](https://github.com/t54-labs/AgenticRiskStandard)
`SettlementLayer` and `CollateralVault` abstract base classes against
the Telaro Anchor program on Solana.

The TypeScript reference implementation is
[`@telaro/ars-solana`](https://www.npmjs.com/package/@telaro/ars-solana)
on npm. This package mirrors the same surface for Python ARS consumers.

## Install

```bash
pip install telaro-ars
```

Requires Python 3.10+ and brings in `solders` for `Pubkey` / `Instruction`
primitives.

## What you get

| File | Role |
| --- | --- |
| `abc.py` | `SettlementLayer` / `CollateralVault` ABCs, mirrored from t54 upstream |
| `events.py` | Principal-track event types (`JobOpened`, `UnderwritingDecided`, ...) |
| `state.py` | `replay()` / `apply_event()`. Pure, no chain. Mirrors `src/state.ts` byte for byte. |
| `binding.py` | `*_intent` describes the on-chain call; `build_view_bond_ix` encodes it for v0.1 |
| `settlement.py` | `TelaroSettlement` concrete impl + `TELARO_SETTLEMENT_MAP` |
| `constants.py` | Program id, bond floor, leverage cap |

## 10-second look

```python
from telaro_ars import (
    JobOpened, UnderwritingStarted, UnderwritingDecided,
    PrincipalReleased, EvidenceSubmitted, Closed,
    replay,
)

log = [
    JobOpened(
        job_id="job-1", at=1,
        agent="AgentPubkey...", requestor="DAppPubkey...",
        exposure_atomic=1_000_000_000,
    ),
    UnderwritingStarted(job_id="job-1", at=2),
    UnderwritingDecided(job_id="job-1", at=3, passed=True),
    PrincipalReleased(job_id="job-1", at=4, amount_atomic=1_000_000_000),
    EvidenceSubmitted(
        job_id="job-1", at=5, action_hash="0xabc", outcome="success",
    ),
    Closed(job_id="job-1", at=6, resolution="no_dispute"),
]

job = replay(log)
print(job.state)            # "CLOSED"
print(job.released_atomic)  # 1_000_000_000
```

`replay` is pure: same log in, same `Job` out.

## Subclassing the SettlementLayer

```python
from telaro_ars import (
    SettlementLayer,
    LockCollateralParams,
    PROGRAM_ID_DEVNET,
    build_view_bond_ix,
)
from solders.pubkey import Pubkey

# Drop-in: subclass the upstream ABC, get a Telaro-backed
# implementation. lock_collateral builds a real view_bond instruction.
class MySettlement(SettlementLayer):
    async def lock_collateral(self, job_id, agent_id, amount):
        return build_view_bond_ix(
            LockCollateralParams(
                job_id=job_id,
                agent=Pubkey.from_string(agent_id),
                min_bond_atomic=amount,
                min_score=700,
            )
        )
    # ... other methods
```

Or use the bundled concrete class:

```python
from telaro_ars import TelaroSettlement

s = TelaroSettlement()
intent = await s.lock_collateral(
    job_id="job-1",
    agent_id="4Nd1mYJgC7DsB3v9pkM9CRZxoUTfXn1kbm1zFM5hZRgM",
    amount=1_000_000_000,
)
# -> InstructionIntent(method="view_bond", ..., args={...})
```

## v0.2 scope

All five in-scope `SettlementLayer` methods (principal track) ship
with fully-encoded `Instruction` builders that produce a valid
Solana `solders.instruction.Instruction` against the Telaro Anchor
program:

| ABC method | Builder |
| --- | --- |
| `lock_collateral` | `build_view_bond_ix` |
| `slash_collateral` | `build_resolve_claim_ix` |
| `unlock_collateral` | `build_withdraw_bond_ix` |
| `pay_premium` | `build_process_pool_yield_ix` |
| `release_principal` | `build_request_credit_ix` |

PDAs (bond vault, deposit vault, credit line, pool config, pool
vault, pool mint authority) are derived in-package against the seeds
pinned in SPEC.md §3; the Python side and the TypeScript reference
produce identical addresses for the same inputs.

The three fee-track methods (`lock_fee`, `release_fee`, `refund_fee`)
remain out of scope per SPEC.md §1 and §10 (deferred).

## Conformance with the TypeScript reference

The `apply_event` transition table here is line-for-line equivalent
to `applyEvent` in `src/state.ts`. The mapping table in
`settlement.py` (`TELARO_SETTLEMENT_MAP`) is the same one pinned in
`src/settlement.ts`. The discriminator for `view_bond` matches the
on-chain Anchor program by construction (`sha256('global:view_bond')[:8]`).

A conformance-test corpus that exercises both sides lives in
`tests/test_state.py` here and `tests/state.test.ts` in the npm
package.

## License

MIT. See [LICENSE](../LICENSE) in the parent repo.
