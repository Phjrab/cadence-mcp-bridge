"""Operator-only fixed library ancestor provisioning; never a public MCP tool."""

from __future__ import annotations

import argparse
import base64
import json
import shlex
from pathlib import Path
from typing import Any

from cadence_mcp_bridge.domain_provisioning import _canonical
from cadence_mcp_bridge.environments import EnvironmentProfile
from cadence_mcp_bridge.onboarding import _local_path
from cadence_mcp_bridge.operator_confirmation import _ssh
from cadence_mcp_bridge.operator_transport import run_fixed
from cadence_mcp_bridge.physical_metadata import _load_bundle, _payload, _resource, _sha
from cadence_mcp_bridge.ssh_backend import OpenSshBackend


def _bootstrap(payload_sha: str, pins: dict[str, str], known: dict[str, str]) -> str:
    return (
        "import sys\n"
        "entry=sys.path[0] if sys.path else None\n"
        "sys.path[:]=[p for p in sys.path if p and p!=entry]\n"
        "import os\n"
        "sys.path[:]=[p for p in sys.path if os.path.isabs(p) and "
        "os.path.realpath(p)!=os.path.realpath(os.getcwd())]\n"
        "import json,hashlib,base64,types,signal\n"
        "signal.alarm(55)\n"
        "raw=sys.stdin.read(1048577).encode('ascii')\n"
        "assert len(raw)<=1048576\n"
        f"assert hashlib.sha256(raw).hexdigest()=={payload_sha!r}\n"
        "data=json.loads(raw.decode('ascii'))\n"
        "assert set(data)==set(('request','sources'))\n"
        f"pins={pins!r}\n"
        "assert set(data['sources'])==set(pins)\n"
        "loaded={}\n"
        "for name in ('setup','collector','core','recipe'):\n"
        " source=base64.b64decode(data['sources'][name])\n"
        " assert hashlib.sha256(source).hexdigest()==pins[name]\n"
        " module=types.ModuleType('physical_ancestor_'+name)\n"
        " module.__dict__['__package__']=None\n"
        " eval(compile(source,'physical_ancestor_'+name+'.py','exec'),module.__dict__)\n"
        " loaded[name]=module\n"
        "encoded=data['request']['files']\n"
        "assets=dict((name,base64.b64decode(value)) for name,value in encoded.items())\n"
        f"result=loaded['recipe'].run(data['request'],loaded['setup'],assets,{known!r},"
        "loaded['collector'],loaded['core'])\n"
        "sys.stdout.write(json.dumps(result,sort_keys=True,separators=(',',':'))+chr(10))\n"
    )


def invoke(
    bundle: Path,
    expected: str,
    operation: str,
    output: Path,
    *,
    plan_path: Path | None = None,
    plan_sha256: str | None = None,
    authority: str | None = None,
) -> dict[str, Any]:
    """Plan is read-only; apply/rollback require the exact saved plan and delegation."""
    if operation not in ("plan", "apply", "rollback"):
        raise ValueError("ancestor_recipe_operation")
    assets, known = _load_bundle(bundle, expected)
    environment = EnvironmentProfile.model_validate_json(assets["profile.json"])
    mutation = None
    if operation != "plan":
        if plan_path is None or not authority or not plan_sha256:
            raise ValueError("ancestor_recipe_explicit_plan_required")
        plan = json.loads(_payload(plan_path))
        if _sha(_canonical(plan)) != plan_sha256:
            raise ValueError("ancestor_recipe_plan_binding")
        mutation = {
            "plan": plan,
            "expected_plan_sha256": plan_sha256,
            "operator_authority": authority,
        }
    elif any(value is not None for value in (plan_path, plan_sha256, authority)):
        raise ValueError("ancestor_recipe_plan_arguments")
    sources = {
        "setup": _resource("_native_setup.py"),
        "collector": _resource("_physical_metadata.py"),
        "core": assets["modeltrust.py"],
        "recipe": _resource("_physical_ancestor_repair.py"),
    }
    request = {
        "operation": operation,
        "manifest_sha256": expected,
        "files": {name: base64.b64encode(data).decode("ascii") for name, data in assets.items()},
        "mutation": mutation,
    }
    raw = _canonical(
        {
            "request": request,
            "sources": {
                name: base64.b64encode(data).decode("ascii") for name, data in sources.items()
            },
        }
    )
    if len(raw) > 1048576:
        raise ValueError("ancestor_recipe_request_bound")
    output = _local_path(output)
    output.mkdir(mode=0o700, exist_ok=False)

    def save(name: str, data: bytes) -> None:
        with (output / name).open("xb") as stream:
            stream.write(data)
        (output / name).chmod(0o600)

    save("request.private.json", raw)
    pins = {name: _sha(source) for name, source in sources.items()}
    try:
        code, stdout, stderr = run_fixed(
            _ssh(environment) + ["-c", shlex.quote(_bootstrap(_sha(raw), pins, known))],
            raw,
            OpenSshBackend._ssh_environment(),
            timeout=60,
            limit=1048576,
        )
        save("stdout.private.log", stdout)
        save("stderr.private.log", stderr)
        if code or stderr:
            raise ValueError("ancestor_recipe_remote_rejected")
        result = json.loads(stdout.splitlines()[-1])
        if operation == "plan":
            if (
                set(result) != {"plan", "plan_sha256"}
                or _sha(_canonical(result["plan"])) != result["plan_sha256"]
            ):
                raise ValueError("ancestor_recipe_response_binding")
            save("plan.private.json", _canonical(result["plan"]))
        elif result != {
            "status": "PHYSICAL_ANCESTOR_METADATA_COMPLETE",
            "execution_authorized": False,
        }:
            raise ValueError("ancestor_recipe_response_shape")
        save("result.private.json", _canonical(result))
        return result  # type: ignore[no-any-return]
    except Exception:
        save("failed.private.json", _canonical({"status": "FAILED_OR_PARTIAL_RETAIN_EVIDENCE"}))
        raise ValueError("ancestor_recipe_failed_or_partial_see_private_evidence") from None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "apply", "rollback"))
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--plan-sha256")
    parser.add_argument("--authority")
    args = parser.parse_args()
    result = invoke(
        args.bundle,
        args.manifest_sha256,
        args.operation,
        args.output,
        plan_path=args.plan,
        plan_sha256=args.plan_sha256,
        authority=args.authority,
    )
    # Private plan/raw events remain local; terminal stdout contains no VM paths.
    print(
        json.dumps(
            {
                "operation": args.operation,
                "completed": True,
                "plan_sha256": result.get("plan_sha256"),
                "eda_execution": False,
            }
        )
    )


if __name__ == "__main__":
    main()
