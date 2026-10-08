"""Bounded operator ledger observations; descriptions never authorize spending."""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, model_validator

from cadence_mcp_bridge.models import ContractModel
from cadence_mcp_bridge.native_diagnostics import OperationId


class FreshResourcePolicy(ContractModel):
    campaign_id: OperationId
    attempt_ceiling: Annotated[int, Field(strict=True, ge=1, le=500)]
    result_ceiling_bytes: Annotated[int, Field(strict=True, ge=1, le=10 * 1024**3)]


class FreshResourceCounter(ContractModel):
    campaign_id: OperationId
    count: Annotated[int, Field(strict=True, ge=0, le=500)]
    result_reserved_bytes: Annotated[int, Field(strict=True, ge=0, le=10 * 1024**3)]
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
