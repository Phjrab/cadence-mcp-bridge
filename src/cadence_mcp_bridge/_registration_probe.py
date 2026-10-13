"""Fixed read-only normal-user registration fingerprint collector; Python2.6."""
# mypy: ignore-errors
import base64
import hashlib
import json
import os
import socket
import sys
import types

LIMIT = 524288


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("ascii")


def inside(path, root):
    return path == root or path.startswith(root + "/")


def collect(request, copying, modeltrust):
    import pwd
    if os.getuid() == 0 or socket.gethostname() != request["hostname"] or (
            pwd.getpwuid(os.getuid()).pw_name != request["user"]):
        raise ValueError("registration_operator_identity")
    workspace, managed = request["workspace_root"], request["managed_root"]
    protected = request["protected_roots"]
    for source in (request["source_cell"], request["source_state"]):
        if not inside(source, workspace) or inside(source, managed) or any(
                inside(source, root) for root in protected):
            raise ValueError("registration_source_scope")
        copying.path(source)
    for library in request["libraries"]:
        path = copying.path(library["path"])
        if inside(path, managed) or not any(inside(path, root) for root in [workspace] + protected):
            raise ValueError("registration_library_scope")
    for include in request["model_includes"]:
        copying.path(include["path"])
        if not any(inside(include["path"], root) for root in protected):
            raise ValueError("registration_model_scope")

    def observation():
        source = copying.snapshot(request["source_cell"])
        state = copying.snapshot(request["source_state"])
        libraries, models = [], {}
        entries, size = source["entries"] + state["entries"], source["bytes"] + state["bytes"]
        for library in request["libraries"]:
            snap = copying.dependency_snapshot(library["path"])
            entries, size = entries + snap["entries"], size + snap["bytes"]
            if entries > 32768 or size > 268435456:
                raise ValueError("registration_total_bound")
            libraries.append(dict(name=library["name"], path=library["path"],
                                  tree_sha256=snap["tree_sha256"]))
        for include in request["model_includes"]:
            graph = modeltrust.trusted_model_graph(include["path"], include["section"])
            for path, sha in graph.items():
                if not any(inside(path, root) for root in protected) or (
                        path in models and models[path] != sha):
                    raise ValueError("registration_model_dependency_scope")
                models[path] = sha
            if len(models) > 128:
                raise ValueError("registration_model_bound")
        return dict(source_tree_sha256=source["tree_sha256"],
                    ade_state_tree_sha256=state["tree_sha256"], libraries=libraries,
                    model_files=[dict(path=p, file_sha256=models[p]) for p in sorted(models)],
                    entries=entries, content_bytes=size)

    first = observation()
    if first != observation():
        raise ValueError("registration_observation_drift")
    return dict(first, schema_version=1, status="REGISTRATION_FINGERPRINTS_OBSERVED",
                operator_uid=os.getuid(), new_simulations=0, new_reservations=0,
                execution_authorized=False)


def main(known):
    try:
        raw = sys.stdin.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("request_bound")
        request = json.loads(raw)
        if canonical(request).decode("ascii") != raw or set(request) != set(("request", "assets")):
            raise ValueError("request_shape")
        if set(request["assets"]) != set(known):
            raise ValueError("asset_shape")
        modules = {}
        for name in sorted(known):
            data = base64.b64decode(request["assets"][name])
            if hashlib.sha256(data).hexdigest() != known[name]:
                raise ValueError("asset_identity")
            module = types.ModuleType("registration_" + name)
            eval(compile(data, "<fixed-registration-asset>", "exec"), module.__dict__)
            modules[name] = module
        result = collect(request["request"], modules["copying"], modules["modeltrust"])
        sys.stdout.write(canonical(result).decode("ascii"))
    except (ValueError, IOError, OSError, KeyError, TypeError):
        sys.stdout.write('{"status":"blocked","reason":"registration_fingerprint_rejected"}')
        sys.exit(1)
