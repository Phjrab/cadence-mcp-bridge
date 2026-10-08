"""Fixed worker's bounded protected OA/ADE tree observation and owned copy.

Operator registration supplies the source and expected hash, never MCP input.
This asset has no CLI, authority, reservation, library discovery or EDA launch.
"""

# mypy: ignore-errors
import hashlib
import json
import os
import re
import stat

MAX_ENTRIES = 4096
MAX_BYTES = 67108864
MAX_DEPTH = 16


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def digest(value):
    return hashlib.sha256(value).hexdigest()


def identity(info):
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_size,
        "%.9f" % info.st_mtime,
    )


def path(value):
    if (
        not os.path.isabs(value)
        or os.path.abspath(value) != value
        or os.path.realpath(value) != value
    ):
        raise ValueError("native_copy_canonical_path")
    return value


def directory(value):
    path(value)
    info = os.lstat(value)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("native_copy_directory_type")
    return info


def blocked(name):
    lower = name.lower()
    return (
        lower.endswith((".cdslck", ".cdslck.old", ".lock", ".panic", ".recovery"))
        or ".cdslck." in lower
        or lower.startswith(("panic", "recovery"))
    )


def read_leaf(value, expected, limit, observation_link=False):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(value, flags)
    stream = os.fdopen(fd, "rb")
    try:
        before = os.fstat(fd)
        if (
            identity(before) != identity(expected)
            or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != (expected.st_nlink if observation_link else 1)
        ):
            raise ValueError("native_copy_file_identity")
        data = stream.read(limit + 1)
        after = os.lstat(value)
        if (
            len(data) > limit
            or identity(after) != identity(before)
            or after.st_nlink != (before.st_nlink if observation_link else 1)
        ):
            raise ValueError("native_copy_file_drift_or_size")
        return data
    finally:
        stream.close()


def _snapshot(source, dependency=False):
    source = path(source)
    metadata = []
    content = []
    total = [0]

    def observe(current, relative, depth):
        if depth > MAX_DEPTH or len(metadata) >= MAX_ENTRIES:
            raise ValueError("native_copy_tree_bound")
        before = directory(current)
        # inode/dev protect a single read; stable manifests retain owner/mode/mtime.
        metadata.append(
            [
                "directory",
                relative,
                stat.S_IMODE(before.st_mode),
                before.st_uid,
                before.st_gid,
                "%.9f" % before.st_mtime,
            ]
        )
        content.append(["directory", relative])
        names = sorted(os.listdir(current))
        for name in names:
            if blocked(name) and not dependency:
                raise ValueError("native_copy_active_or_recovery_artifact")
            selected = os.path.join(current, name)
            child = name if not relative else relative + "/" + name
            info = os.lstat(selected)
            if stat.S_ISDIR(info.st_mode):
                observe(selected, child, depth + 1)
            elif stat.S_ISREG(info.st_mode):
                if len(metadata) >= MAX_ENTRIES or (
                    info.st_nlink != 1 and not (dependency and blocked(name))
                ):
                    raise ValueError("native_copy_tree_or_link_bound")
                data = (
                    read_leaf(selected, info, MAX_BYTES - total[0], True)
                    if dependency and blocked(name)
                    else read_leaf(selected, info, MAX_BYTES - total[0])
                )
                total[0] += len(data)
                sha = digest(data)
                metadata.append(
                    [
                        "file",
                        child,
                        stat.S_IMODE(info.st_mode),
                        info.st_uid,
                        info.st_gid,
                        "%.9f" % info.st_mtime,
                        len(data),
                        sha,
                    ]
                )
                if dependency:
                    metadata[-1].append(info.st_nlink)
                content.append(["file", child, len(data), sha])
            else:
                raise ValueError("native_copy_link_or_special_file")
        if identity(directory(current)) != identity(before) or sorted(os.listdir(current)) != names:
            raise ValueError("native_copy_directory_drift")

    observe(source, "", 0)
    return {
        "schema_version": 2 if dependency else 1,
        "tree_sha256": digest(canonical(metadata)),
        "content_sha256": digest(canonical(content)),
        "entries": len(metadata),
        "bytes": total[0],
        "metadata": metadata,
    }


def snapshot(source):
    return _snapshot(source)


def dependency_snapshot(source):
    """Read-only library preservation observation, never a source-copy permission.

    Existing regular lock/recovery evidence may have hardlink aliases. Observe
    their exact content/metadata/link counts without removing or copying them.
    Code/OA hardlinks, symlinks and special files still reject. The strict
    snapshot/copy_owned route remains unchanged and rejects every busy source.
    """
    return _snapshot(source, True)


def sync(directory_path):
    if os.name == "nt":
        return  # Disposable Windows tests do not attest POSIX persistence.
    fd = os.open(directory_path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def owned_parent(parent):
    current = path(parent)
    first = True
    while True:
        info = directory(current)
        if os.name != "nt" and (
            info.st_uid not in ((os.getuid(),) if first else (0, os.getuid()))
            or info.st_mode & (63 if first else 18)
        ):
            raise ValueError("native_copy_destination_trust")
        first = False
        ancestor = os.path.dirname(current)
        if current == ancestor:
            break
        current = ancestor


def copy_owned(source, target, expected_tree_sha256):
    # The fixed provider must bind source/target to confirmed registration/UUID.
    source = path(source)
    target = path(target)
    parent = os.path.dirname(target)
    owned_parent(parent)
    if source == target or source.startswith(target + os.sep) or target.startswith(source + os.sep):
        raise ValueError("native_copy_source_destination_overlap")
    before = snapshot(source)
    if before["tree_sha256"] != expected_tree_sha256:
        raise ValueError("native_copy_source_registration_mismatch")
    if os.path.lexists(target):
        raise ValueError("native_copy_destination_already_exists")
    os.mkdir(target, 448)
    sync(parent)
    for item in before["metadata"]:
        if item[1] == "":
            continue
        selected = os.path.join(target, *item[1].split("/"))
        if item[0] == "directory":
            owned_parent(os.path.dirname(selected))
            os.mkdir(selected, 448)
            sync(os.path.dirname(selected))
        else:
            original = os.path.join(source, *item[1].split("/"))
            info = os.lstat(original)
            expected = [
                "file",
                item[1],
                stat.S_IMODE(info.st_mode),
                info.st_uid,
                info.st_gid,
                "%.9f" % info.st_mtime,
                info.st_size,
                item[-1],
            ]
            if expected != item:
                raise ValueError("native_copy_source_metadata_drift")
            data = read_leaf(original, info, min(MAX_BYTES, info.st_size))
            if digest(data) != item[-1]:
                raise ValueError("native_copy_source_content_drift")
            owned_parent(os.path.dirname(selected))
            fd = os.open(selected, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 384)
            stream = os.fdopen(fd, "wb")
            try:
                stream.write(data)
                stream.flush()
                os.fsync(fd)
            finally:
                stream.close()
            sync(os.path.dirname(selected))
    after = snapshot(source)
    copied = snapshot(target)
    if after != before or copied["content_sha256"] != before["content_sha256"]:
        raise ValueError("native_copy_preservation_or_content_mismatch")
    return {
        "schema_version": 1,
        "source_tree_sha256": before["tree_sha256"],
        "source_content_sha256": before["content_sha256"],
        "copy_content_sha256": copied["content_sha256"],
        "copy_tree_sha256": copied["tree_sha256"],
        "source_preserved": True,
        "copy_owned": True,
        "entries": copied["entries"],
        "bytes": copied["bytes"],
    }


def remap_ade_info(data, source_binding, target_binding, project):
    # Only the owned state's two routing fields change. The caller must attest
    # the source/copy snapshots and exclusively write the returned owned bytes.
    try:
        strings = (basestring,)
    except NameError:
        strings = (str,)
    for bindings in (source_binding, target_binding):
        if type(bindings) not in (tuple, list) or len(bindings) != 3:
            raise ValueError("native_copy_state_binding")
        for value in bindings:
            if (
                not isinstance(value, strings)
                or not re.match(r"^[A-Za-z][A-Za-z0-9_#-]{0,63}$", value)
                or "\n" in value
            ):
                raise ValueError("native_copy_state_binding")
    if (
        not isinstance(project, strings)
        or not re.match(r"^/[A-Za-z0-9_#./-]{1,511}$", project)
        or "\n" in project
        or any(p in ("", ".", "..") for p in project[1:].split("/"))
    ):
        raise ValueError("native_copy_state_project")
    if len(data) > 65536:
        raise ValueError("native_copy_state_info_bound")
    text = data.decode("latin-1")
    info = list(
        re.finditer(
            r'^designInfo = \'\("([A-Za-z][A-Za-z0-9_#-]{0,63})" '
            r'"([A-Za-z][A-Za-z0-9_#-]{0,63})" "([A-Za-z][A-Za-z0-9_#-]{0,63})" "spectre"\)$',
            text,
            re.M,
        )
    )
    routing = list(re.finditer('^projectDir = \'"([^"\\r\\n]{1,512})"$', text, re.M))
    if len(info) != 1 or len(routing) != 1 or tuple(info[0].groups()) != tuple(source_binding):
        raise ValueError("native_copy_state_routing_mismatch")
    replacement = "designInfo = '(\"" + '" "'.join(target_binding) + '" "spectre")'
    project_line = "projectDir = '\"" + project + '"'
    edits = sorted(
        [
            (info[0].start(), info[0].end(), replacement),
            (routing[0].start(), routing[0].end(), project_line),
        ],
        reverse=True,
    )
    for start, end, value in edits:
        text = text[:start] + value + text[end:]
    return text.encode("latin-1")
