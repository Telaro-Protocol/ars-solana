"""
ARS abstract base classes, mirrored from t54-labs/AgenticRiskStandard.

The upstream Python package isn't on pypi yet, so we mirror the
relevant ABC surface here. When upstream publishes, callers may
substitute upstream's ABCs and our concrete `TelaroSettlement` will
still satisfy them (the method signatures match upstream byte-for-
byte).

Scope: principal track only. The fee-track methods are intentionally
omitted from this v0.1 mirror, matching the ARS-Solana Profile v0.1
deferral (SPEC.md sections 1 and 10).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DepositStatus(str, Enum):
    """Vault deposit lifecycle, mirroring `abstract_ars.vault.DepositStatus`."""

    LOCKED = "LOCKED"
    RELEASED = "RELEASED"
    REFUNDED = "REFUNDED"
    SLASHED = "SLASHED"


@dataclass(frozen=True)
class DepositInfo:
    """Vault deposit snapshot, mirroring `abstract_ars.vault.DepositInfo`."""

    job_id: str
    amount: int
    asset: str
    status: DepositStatus
    locked_at: int | None = None
    released_at: int | None = None


class CollateralVault(ABC):
    """Collateral lock / unlock / slash. Telaro maps this onto BondAccount."""

    @abstractmethod
    async def lock(self, job_id: str, agent_id: str, amount: int) -> Any:
        """Treat the agent's standing bond as locked against the job."""

    @abstractmethod
    async def unlock(self, job_id: str, agent_id: str) -> Any:
        """Release the bond once the job closes."""

    @abstractmethod
    async def slash(self, job_id: str, agent_id: str, payee: str, amount: int) -> Any:
        """Pay the harmed party out of the agent's bond."""

    @abstractmethod
    async def get_status(self, job_id: str) -> DepositInfo:
        """Read the current `DepositInfo` for the job."""


class SettlementLayer(ABC):
    """
    The ARS settlement surface. Telaro implements the six in-scope
    methods against the on-chain Anchor program; the three fee-track
    methods are deferred to ARS-Solana Profile v0.2.

    Method signatures intentionally mirror upstream `abstract_ars/`
    so an implementation may inherit from either ABC interchangeably.
    """

    # -------- principal-track methods (in scope for v0.1) --------

    @abstractmethod
    async def lock_collateral(
        self, job_id: str, agent_id: str, amount: int
    ) -> Any:
        ...

    @abstractmethod
    async def slash_collateral(
        self, job_id: str, agent_id: str, payee: str, amount: int
    ) -> Any:
        ...

    @abstractmethod
    async def unlock_collateral(self, job_id: str, agent_id: str) -> Any:
        ...

    @abstractmethod
    async def pay_premium(
        self,
        job_id: str,
        payer: str,
        underwriter: str,
        amount: int,
    ) -> Any:
        ...

    @abstractmethod
    async def release_principal(
        self, job_id: str, agent_id: str, amount: int
    ) -> Any:
        ...
