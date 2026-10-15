"""Local immutable design plans; independent of execution and resource journals."""

from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from cadence_mcp_bridge.native_diagnostics import OperationId
from cadence_mcp_bridge.schematic_plan import (
    DeviceRegistry,
    PlanDryRun,
    RevisionBinding,
    SchematicPlan,
    dry_run_plan,
)
from cadence_mcp_bridge.variable_contracts import Digest, LogicalId, VariableModel, canonical_digest

APPLICATION_ID = 0x4D325231
MAX_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 1000


class RevisionRejected(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class RevisionRecord(VariableModel):
    schema_version: Literal[1] = 1
    plan: SchematicPlan
    registry: DeviceRegistry
    validation: PlanDryRun
    status: Literal["draft", "plan_validated"]
    execution_authorized: Literal[False] = False

    @model_validator(mode="after")
    def bindings(self) -> RevisionRecord:
        if (
            self.validation.binding != self.plan.binding
            or self.validation.plan_sha256 != self.plan.plan_sha256
            or self.validation.semantic_sha256 != self.plan.semantic_sha256
            or self.validation.registry_sha256 != self.registry.semantic_sha256
            or self.plan.registry_sha256 != self.registry.semantic_sha256
            or self.status
            != (
                "plan_validated"
                if self.validation.status == "LOCAL_SYNTHETIC_PLAN_VALID"
                else "draft"
            )
        ):
            raise ValueError("revision validation binding mismatch")
        return self

    @property
    def revision_sha256(self) -> str:
        return canonical_digest(self)


class RevisionEvidence(VariableModel):
    """External reference, never a locally minted verification or resource claim."""

    evidence_id: LogicalId
    binding: RevisionBinding
    revision_sha256: Digest
    semantic_sha256: Digest
    kind: Literal["simulation", "measurement", "erc", "drc", "lvs", "pex", "post_layout"]
    operation_id: OperationId
    result_sha256: Digest
    reported_outcome: Literal["pass", "fail", "unknown"]
    provenance: Literal["operator_supplied_reference_unverified"] = (
        "operator_supplied_reference_unverified"
    )


def _guard(path: Path, *, existing: bool) -> None:
    for item in (path, *path.parents):
        if item.is_symlink() or item.is_junction():
            raise RevisionRejected("revision_store_links_denied")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if existing:
            raise RevisionRejected("revision_store_not_initialized") from None
        return
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > MAX_BYTES:
        raise RevisionRejected("revision_store_invalid_file")


class RevisionStore:
    """Own DB identity; never creates tables in an operational analysis/sweep DB.

    BEGIN IMMEDIATE and immutable IDs make same-plan retries idempotent and
    competing revisions deterministic. This is local metadata, not an OA txn.
    """

    def __init__(self, path: Path) -> None:
        self.path = path.absolute()

    def initialize(self) -> None:
        _guard(self.path, existing=False)
        for suffix in ("-journal", "-wal", "-shm"):
            sidecar = self.path.with_name(self.path.name + suffix)
            _guard(sidecar, existing=False)
            if sidecar.exists() and not self.path.exists():
                raise RevisionRejected("orphan_revision_sidecar")
        if not self.path.parent.is_dir():
            raise RevisionRejected("revision_store_parent_required")
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            with self.connection(write=False):
                return
        os.close(descriptor)
        # A failed initialization remains visible and cannot be adopted later.
        with sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True) as connection:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute("PRAGMA user_version=1")
            connection.execute(
                "CREATE TABLE revisions (workspace TEXT, design TEXT, revision TEXT, "
                "digest TEXT NOT NULL, payload TEXT NOT NULL, "
                "PRIMARY KEY(workspace, design, revision))"
            )
            connection.execute(
                "CREATE TABLE evidence (evidence_id TEXT PRIMARY KEY, "
                "revision_digest TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    @contextmanager
    def connection(self, *, write: bool) -> Iterator[sqlite3.Connection]:
        _guard(self.path, existing=True)
        for suffix in ("-journal", "-wal", "-shm"):
            _guard(self.path.with_name(self.path.name + suffix), existing=False)
        # Even a PRAGMA read can recover a foreign hot journal before returning.
        # Inspect the fixed header without SQLite first. This store uses rollback
        # journals only; WAL readers can create SHM files, so reject that format.
        with self.path.open("rb") as stream:
            header = stream.read(100)
        if (
            len(header) != 100
            or header[:16] != b"SQLite format 3\x00"
            or int.from_bytes(header[68:72], "big") != APPLICATION_ID
            or int.from_bytes(header[60:64], "big") != 1
        ):
            raise RevisionRejected("foreign_database_denied")
        if header[18:20] != b"\x01\x01":
            raise RevisionRejected("revision_journal_mode_unsupported")
        connection = sqlite3.connect(
            self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
            uri=True,
            timeout=5,
        )
        try:
            # Identify before any persistent pragma or schema mutation.
            if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID or (
                connection.execute("PRAGMA user_version").fetchone()[0] != 1
            ):
                raise RevisionRejected("foreign_database_denied")
            tables = {
                r[0]
                for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if tables != {"revisions", "evidence"}:
                raise RevisionRejected("revision_schema_mismatch")
            if write:
                connection.execute("PRAGMA synchronous=FULL")
                page_size = connection.execute("PRAGMA page_size").fetchone()[0]
                page_limit = MAX_BYTES // page_size
                if page_limit < connection.execute("PRAGMA page_count").fetchone()[0]:
                    raise RevisionRejected("revision_store_capacity")
                connection.execute(f"PRAGMA max_page_count={page_limit}")
                connection.execute("BEGIN IMMEDIATE")
            else:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("BEGIN")
            yield connection
            if write:
                if connection.execute("PRAGMA page_count").fetchone()[0] * page_size > MAX_BYTES:
                    raise RevisionRejected("revision_store_capacity")
                connection.commit()
        finally:
            connection.rollback()
            connection.close()

    @staticmethod
    def _read(
        connection: sqlite3.Connection,
        workspace: str,
        design: str,
        revision: str,
        ancestors: tuple[str, ...] = (),
    ) -> RevisionRecord:
        if revision in ancestors or len(ancestors) >= 64:
            raise RevisionRejected("revision_parent_cycle_or_depth")
        row = connection.execute(
            "SELECT digest,payload FROM revisions WHERE workspace=? AND design=? AND revision=?",
            (workspace, design, revision),
        ).fetchone()
        if row is None:
            raise RevisionRejected("revision_not_found")
        if len(row[1]) > 1_048_576:
            raise RevisionRejected("revision_payload_size_limit")
        result = RevisionRecord.model_validate_json(row[1])
        binding = result.plan.binding
        if result.revision_sha256 != row[0] or (
            binding.workspace_id,
            binding.design_id,
            binding.revision_id,
        ) != (workspace, design, revision):
            raise RevisionRejected("revision_digest_mismatch")
        parent = None
        if binding.parent_revision_id is not None:
            parent = RevisionStore._read(
                connection, workspace, design, binding.parent_revision_id, (*ancestors, revision)
            )
            if parent.revision_sha256 != binding.parent_revision_sha256:
                raise RevisionRejected("parent_revision_digest_mismatch")
        checked = dry_run_plan(
            result.plan, result.registry, binding, baseline=parent.plan if parent else None
        )
        if checked != result.validation:
            raise RevisionRejected("revision_validation_mismatch")
        return result

    def read(self, workspace: str, design: str, revision: str) -> RevisionRecord:
        with self.connection(write=False) as connection:
            return self._read(connection, workspace, design, revision)

    def add(
        self, plan: SchematicPlan, registry: DeviceRegistry, expected_binding: RevisionBinding
    ) -> RevisionRecord:
        plan = SchematicPlan.model_validate_json(plan.model_dump_json())
        registry = DeviceRegistry.model_validate_json(registry.model_dump_json())
        expected_binding = RevisionBinding.model_validate_json(expected_binding.model_dump_json())
        binding = plan.binding
        with self.connection(write=True) as connection:
            parent = None
            if binding.parent_revision_id is not None:
                parent = self._read(
                    connection,
                    binding.workspace_id,
                    binding.design_id,
                    binding.parent_revision_id,
                    (binding.revision_id,),
                )
                if binding.parent_revision_sha256 != parent.revision_sha256:
                    raise RevisionRejected("parent_revision_digest_mismatch")
            validation = dry_run_plan(
                plan, registry, expected_binding, baseline=parent.plan if parent else None
            )
            record = RevisionRecord(
                plan=plan,
                registry=registry,
                validation=validation,
                status="plan_validated"
                if validation.status == "LOCAL_SYNTHETIC_PLAN_VALID"
                else "draft",
            )
            row = connection.execute(
                "SELECT digest FROM revisions WHERE workspace=? AND design=? AND revision=?",
                (binding.workspace_id, binding.design_id, binding.revision_id),
            ).fetchone()
            if row:
                existing = self._read(
                    connection, binding.workspace_id, binding.design_id, binding.revision_id
                )
                if (
                    existing.plan.plan_sha256 != record.plan.plan_sha256
                    or existing.registry.semantic_sha256 != record.registry.semantic_sha256
                    or existing.validation != record.validation
                ):
                    raise RevisionRejected("immutable_revision_conflict")
                return existing
            if connection.execute("SELECT COUNT(*) FROM revisions").fetchone()[0] >= MAX_RECORDS:
                raise RevisionRejected("revision_store_capacity")
            connection.execute(
                "INSERT INTO revisions VALUES(?,?,?,?,?)",
                (
                    binding.workspace_id,
                    binding.design_id,
                    binding.revision_id,
                    record.revision_sha256,
                    record.model_dump_json(),
                ),
            )
            return record

    def attach(self, reference: RevisionEvidence) -> None:
        reference = RevisionEvidence.model_validate_json(reference.model_dump_json())
        binding = reference.binding
        with self.connection(write=True) as connection:
            record = self._read(
                connection, binding.workspace_id, binding.design_id, binding.revision_id
            )
            if reference.binding != record.plan.binding or (
                reference.revision_sha256 != record.revision_sha256
                or reference.semantic_sha256 != record.plan.semantic_sha256
            ):
                raise RevisionRejected("evidence_revision_mismatch")
            row = connection.execute(
                "SELECT payload FROM evidence WHERE evidence_id=?", (reference.evidence_id,)
            ).fetchone()
            if row:
                if RevisionEvidence.model_validate_json(row[0]) != reference:
                    raise RevisionRejected("immutable_evidence_conflict")
                return
            if connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] >= MAX_RECORDS:
                raise RevisionRejected("evidence_store_capacity")
            connection.execute(
                "INSERT INTO evidence VALUES(?,?,?)",
                (
                    reference.evidence_id,
                    reference.revision_sha256,
                    reference.model_dump_json(),
                ),
            )

    def evidence(self, workspace: str, design: str, revision: str) -> list[RevisionEvidence]:
        with self.connection(write=False) as connection:
            record = self._read(connection, workspace, design, revision)
            rows = connection.execute(
                "SELECT payload FROM evidence WHERE revision_digest=? ORDER BY evidence_id",
                (record.revision_sha256,),
            )
            references = [RevisionEvidence.model_validate_json(row[0]) for row in rows]
            if any(
                ref.binding != record.plan.binding
                or ref.revision_sha256 != record.revision_sha256
                or ref.semantic_sha256 != record.plan.semantic_sha256
                for ref in references
            ):
                raise RevisionRejected("evidence_revision_mismatch")
            return references
