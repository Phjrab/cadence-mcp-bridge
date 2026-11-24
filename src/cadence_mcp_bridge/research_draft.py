"""Compile a reviewed flat MOS study into the existing research declaration format."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import Field

from cadence_mcp_bridge.domain_provisioning import _closed_document
from cadence_mcp_bridge.research_circuit import (
    Analysis,
    Circuit,
    Evidence,
    Link,
    Master,
    Measurement,
    Mos,
    MosGeometry,
    Name,
    Observation,
    Placement,
    Port,
    ResearchCircuit,
    SpectreMos,
    Symbol,
    Wire,
)
from cadence_mcp_bridge.schematic_plan import RevisionBinding
from cadence_mcp_bridge.variable_contracts import Digest, VariableModel


class DevicePort(VariableModel):
    """Target-PDK choices. Paper geometry never supplies a target-PDK default."""

    name: Name
    kind: Literal["nmos", "pmos"]
    master: Master
    master_source: Evidence
    placement: Placement
    geometry: MosGeometry
    spectre: SpectreMos
    resolved_terminals: dict[Literal["D", "G", "S", "B"], Name] = Field(default_factory=dict)


class DraftPort(VariableModel):
    schema_version: Literal[1]
    draft_sha256: Digest
    source_design: Name
    topology_source: Evidence
    binding: RevisionBinding
    dut: Name
    ports: tuple[Port, ...]
    symbol: Symbol
    wires: tuple[Wire, ...] = ()
    devices: Annotated[tuple[DevicePort, ...], Field(min_length=1, max_length=128)]
    bench: Circuit
    analyses: tuple[Analysis, ...] = ()
    observations: tuple[Observation, ...] = ()
    measurements: tuple[Measurement, ...] = ()


def compile_research_draft(draft_bytes: bytes, port_bytes: bytes) -> ResearchCircuit:
    """Read source topology and explicit porting decisions, with no execution side effects."""
    _closed_document(draft_bytes)
    _closed_document(port_bytes)
    port = DraftPort.model_validate_json(port_bytes)
    if sha256(draft_bytes).hexdigest() != port.draft_sha256:
        raise ValueError("research draft fingerprint differs")
    draft = json.loads(draft_bytes)
    if (
        not isinstance(draft, dict)
        or draft.get("document_kind") != "research-draft-v1"
        or draft.get("execution_ready") is not False
    ):
        raise ValueError("expected a research draft document")
    design = draft.get("design")
    if not isinstance(design, dict) or design.get("name") != port.source_design:
        raise ValueError("source design identity differs")
    pins = design.get("pins_candidates")
    if not isinstance(pins, list) or any(
        not isinstance(pin, dict) or not isinstance(pin.get("name"), str) for pin in pins
    ):
        raise ValueError("source pin list required")
    pin_names = [pin["name"] for pin in pins]
    if len(set(pin_names)) != len(pin_names) or set(pin_names) != {p.name for p in port.ports}:
        raise ValueError("source and target DUT pins differ")
    rows = design.get("devices")
    if not isinstance(rows, list) or len(rows) != len(port.devices):
        raise ValueError("source and target device populations differ")
    choices = {device.name: device for device in port.devices}
    if len(choices) != len(port.devices) or port.topology_source.status != "confirmed":
        raise ValueError("unique target devices and reviewed topology evidence required")

    instances: list[Mos] = []
    nets = {pin.net for pin in port.ports}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            raise ValueError("invalid draft device identity")
        choice = choices.pop(row["name"], None)
        if choice is None or row.get("device_kind_candidate") != choice.kind:
            raise ValueError("unknown, duplicate or mismatched draft device")
        terminals = row.get("terminals")
        if not isinstance(terminals, dict) or terminals.keys() != {"D", "G", "S", "B"}:
            raise ValueError(f"{choice.name} requires four declared terminal slots")
        missing = {terminal for terminal, net in terminals.items() if net is None}
        if missing != choice.resolved_terminals.keys():
            raise ValueError(
                f"{choice.name} requires decisions for exactly its unresolved terminals"
            )
        if any(
            source.status != "confirmed"
            for source in (
                choice.master_source,
                choice.geometry.source,
                choice.spectre.source,
            )
        ):
            raise ValueError(f"{choice.name} lacks reviewed target-PDK evidence")
        resolved = terminals | choice.resolved_terminals
        links = tuple(Link(terminal=name, net=resolved[name]) for name in ("D", "G", "S", "B"))
        nets.update(link.net for link in links)
        instances.append(
            Mos(
                name=choice.name,
                kind=choice.kind,
                links=links,
                master=choice.master,
                master_source=choice.master_source,
                placement=choice.placement,
                geometry=choice.geometry,
                spectre=choice.spectre,
            )
        )
    dut = Circuit(
        name=port.dut,
        nets=tuple(sorted(nets)),
        ports=port.ports,
        symbol=port.symbol,
        instances=tuple(instances),
        wires=port.wires,
    )
    return ResearchCircuit(
        binding=port.binding,
        source=port.topology_source,
        dut=dut.name,
        bench=port.bench.name,
        circuits=(dut, port.bench),
        analyses=port.analyses,
        observations=port.observations,
        measurements=port.measurements,
    )
