from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPROVALS = ROOT / "docs/approvals"
DEPLOY = "WP14_BOUNDED_READ_ONLY_DISCOVERY_DEPLOYMENT_EXECUTION_APPROVAL_PACKAGE"
COLLECT = "WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_APPROVAL_PACKAGE"
SINGLE = "WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_SINGLE_USE_APPROVAL_PACKAGE"
OLD_HASHES = {
    DEPLOY: "7d93fefb96c65dd9a204a4de3fb0dba087ca112edf894bb3ff97e7ee0d3c6f87",
    COLLECT: "1906357b1ef5ba98a3d28241896fc59d0a4ff8053b64eac9f5d45f9a9bde0fcb",
    SINGLE: "648409527484c75b67df50c27eccc4a8e28ce22921750592ab6517b135676b9f",
}


def digest(path: Path) -> str:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode()).hexdigest()


def package(name: str, version: int) -> dict:
    return json.loads((APPROVALS / f"{name}_V{version}.json").read_text(encoding="utf-8"))


def test_predecessors_immutable_and_successors_are_requests_only() -> None:
    for name, old_hash in OLD_HASHES.items():
        assert digest(APPROVALS / f"{name}_V1.json") == old_hash
        new = package(name, 2)
        assert new["package_version"] == 2
        assert new["supersedes"] == {
            "path": f"docs/approvals/{name}_V1.json",
            "normalized_lf_sha256": old_hash,
        }
        assert all(value is False for value in new["authority"].values())
        assert new["public_policy"]["execution_authority"] is False
        assert new["public_policy"]["repository_visibility"] == "public"
        assert new["public_policy"]["fresh_evidence_publication"] == (
            "local_exact_field_review_required_before_git"
        )
        assert len(new["acceptance_criteria"]) == len(package(name, 1)["acceptance_criteria"])


def test_fixed_operation_contracts_and_assets_unchanged() -> None:
    for field in (
        "bound_contracts",
        "deployment_asset_allowlist",
        "proposed_deployment_contract",
        "proposed_invocation_contract",
    ):
        assert package(DEPLOY, 2)[field] == package(DEPLOY, 1)[field]
    for field in (
        "fixed_collection_target",
        "asset_preimage_allowlist",
        "proposed_collector_contract",
        "evidence_schema",
    ):
        assert package(COLLECT, 2)[field] == package(COLLECT, 1)[field]
    assert (
        package(SINGLE, 2)["fixed_future_operation"] == package(SINGLE, 1)["fixed_future_operation"]
    )
    for entry in package(DEPLOY, 2)["deployment_asset_allowlist"]:
        assert digest(ROOT / entry["path"]) == entry["normalized_lf_sha256"]


def test_hash_dependency_chain_and_historical_commit_are_consistent() -> None:
    deployer = ROOT / "scripts/deploy-wp14-narrow.ps1"
    collector = ROOT / "scripts/collect-wp14-remote-preimages.py"
    deploy_hash = digest(APPROVALS / f"{DEPLOY}_V2.json")
    collect_hash = digest(APPROVALS / f"{COLLECT}_V2.json")
    assert f'$packageHash = "{deploy_hash}"' in deployer.read_text(encoding="utf-8")
    binding = package(COLLECT, 2)["repository_binding"]
    assert binding["immutable_deployment_package_normalized_lf_sha256"] == deploy_hash
    assert binding["hardened_deployer_normalized_lf_sha256"] == digest(deployer)
    text = collector.read_text(encoding="utf-8")
    for name, value in (
        ("PACKAGE_HASH", collect_hash),
        ("DEPLOYMENT_PACKAGE_HASH", deploy_hash),
        ("DEPLOYER_HASH", digest(deployer)),
    ):
        assert f'{name} = "{value}"' in text
    single = package(SINGLE, 2)
    assert single["immutable_bindings"]["request_package_normalized_lf_sha256"] == collect_hash
    assert single["immutable_bindings"]["collector_normalized_lf_sha256"] == digest(collector)
    fixed = single["future_activation_record_closed_schema"]["fixed_values"]
    assert fixed["package_normalized_lf_sha256"] == collect_hash
    assert fixed["collector_normalized_lf_sha256"] == digest(collector)
    commit = re.search(r'^REPOSITORY_MAIN_COMMIT = "([a-f0-9]+)"', text, re.M)
    assert commit and fixed["repository_main_commit"] == commit[1]
    assert commit[1] == "e60ab270a5e002256f8c5bbf6b81e54f65c10a31"


def test_public_policy_does_not_activate_operations() -> None:
    assert package(COLLECT, 2)["repository_binding"]["visibility_required"] == "public"
    assert package(DEPLOY, 2)["repository_binding"]["visibility_required"] == "public"
    assert package(SINGLE, 2)["repository_provenance"]["required_visibility"] == "public"
    for name in (
        "WP14_REMOTE_IDENTITY_PREIMAGE_EVIDENCE_COLLECTION_AUTHORIZATION_V1.json",
        "WP14_NARROW_REMOTE_DEPLOYMENT_AUTHORIZATION_V2.json",
    ):
        assert not (APPROVALS / name).exists()
    lineage = json.loads((ROOT / "remote/config/runner-lineage.json").read_text(encoding="utf-8"))
    assert lineage["deployment_enabled"] is False
