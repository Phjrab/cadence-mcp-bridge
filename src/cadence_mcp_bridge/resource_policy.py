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


class RetainedV7ResourcePolicy(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    attempt_ceiling: Literal[500]
    result_ceiling_bytes: Literal[17381195776]
    policy_sha256: Literal["fe0b7682fdc0fa97fd06baf18efcb74dafc8c3aa9e699ea2689ddd068c289a67"]


class RetainedV7ResourceCounter(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    count: Annotated[int, Field(strict=True, ge=138, le=500)]
    result_reserved_bytes: Annotated[int, Field(strict=True, ge=17063477248, le=17381195776)]
    policy: RetainedV7ResourcePolicy


class RetainedV8ResourcePolicy(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    attempt_ceiling: Literal[500]
    result_ceiling_bytes: Literal[17632854016]
    policy_sha256: Literal["939d57d3f038c90d3b3401315c15f8a76fb2c3c6b96410b4dfcf2db5b67c9ad5"]


class RetainedV8ResourceCounter(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    count: Annotated[int, Field(strict=True, ge=140, le=500)]
    result_reserved_bytes: Annotated[int, Field(strict=True, ge=17331912704, le=17632854016)]
    policy: RetainedV8ResourcePolicy


class RetainedV9ResourcePolicy(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    attempt_ceiling: Literal[500]
    result_ceiling_bytes: Literal[17767071744]
    policy_sha256: Literal["4325facb94d3d26982950ebecfa22eb2594270de1cd7168a923d0cf27553ad19"]


class RetainedV9ResourceCounter(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    count: Annotated[int, Field(strict=True, ge=142, le=500)]
    result_reserved_bytes: Annotated[int, Field(strict=True, ge=17600348160, le=17767071744)]
    policy: RetainedV9ResourcePolicy


class RetainedV10ResourcePolicy(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    attempt_ceiling: Literal[500]
    result_ceiling_bytes: Literal[18169724928]
    policy_sha256: Literal["f2f546514a2b2986de399a22f4c18cf05600c4391473ff0fb5a4d481e696da66"]


class RetainedV10ResourceCounter(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    count: Annotated[int, Field(strict=True, ge=143, le=500)]
    result_reserved_bytes: Annotated[int, Field(strict=True, ge=17734565888, le=18169724928)]
    policy: RetainedV10ResourcePolicy


class RetainedV11ResourcePolicy(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    attempt_ceiling: Literal[500]
    result_ceiling_bytes: Literal[18183356416]
    policy_sha256: Literal["5c3bb0fabbad36eb98923851b2a6eaf0f131affad715c8ce6fc2a14ad0f41f74"]


class RetainedV11ResourceCounter(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    count: Annotated[int, Field(strict=True, ge=147, le=500)]
    result_reserved_bytes: Annotated[int, Field(strict=True, ge=18141413376, le=18183356416)]
    policy: RetainedV11ResourcePolicy


class RetainedV12ResourcePolicy(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    attempt_ceiling: Literal[500]
    result_ceiling_bytes: Literal[18200133632]
    policy_sha256: Literal["971001fb558dd65c6bcd966eda109615f8d545cb8e3e4f27f54539da8f87cb93"]


class RetainedV12ResourceCounter(ContractModel):
    campaign_id: Literal["AUTO-PHASE-01"]
    count: Annotated[int, Field(strict=True, ge=148, le=500)]
    result_reserved_bytes: Annotated[int, Field(strict=True, ge=18145607680, le=18200133632)]
    policy: RetainedV12ResourcePolicy
