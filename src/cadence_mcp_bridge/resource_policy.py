"""Bounded operator ledger observations; descriptions never authorize spending."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId


class FreshResourcePolicy(ContractModel):
    campaign_id: OperationId
    attempt_ceiling: Annotated[int, Field(strict=True, ge=1, le=500)]
    result_ceiling_bytes: Annotated[int, Field(strict=True, ge=1, le=16 * 1024**3)]


class FreshResourceCounter(ContractModel):
    campaign_id: OperationId
    count: Annotated[int, Field(strict=True, ge=0, le=500)]
    result_reserved_bytes: Annotated[int, Field(strict=True, ge=0, le=16 * 1024**3)]
    policy: FreshResourcePolicy

    @model_validator(mode="after")
    def policy_binding(self) -> Self:
        if (
            self.campaign_id != self.policy.campaign_id
            or self.count > self.policy.attempt_ceiling
            or self.result_reserved_bytes > self.policy.result_ceiling_bytes
            or (self.count == 0) != (self.result_reserved_bytes == 0)
            or self.result_reserved_bytes < self.count
        ):
            raise ValueError("counter exceeds or differs from registered policy")
        return self


class RetainedResourcePolicy(ContractModel):
    """Explicit current-VM v6 observation; neither a default nor execution consent."""

    campaign_id: Literal["AUTO-PHASE-01"]
    attempt_ceiling: Literal[500]
    result_ceiling_bytes: Literal[17179869184]
    policy_sha256: Literal["1625e131118a0c0b4ff466c567d8a79bcb050dbf798505c23685e7b5604adac0"]


class RetainedResourceCounter(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    count: Annotated[int, Field(strict=True, ge=32, le=500)]
    result_reserved_bytes: Annotated[int, Field(strict=True, ge=3088056320, le=17179869184)]
    policy: RetainedResourcePolicy
