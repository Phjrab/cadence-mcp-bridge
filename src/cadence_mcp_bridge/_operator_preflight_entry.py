"""Fixed held-byte preflight entry; Python2.6, existing shared lock, no writes."""

# mypy: ignore-errors
import sys

if __name__ == "__main__":
    if not sys.flags.ignore_environment or not sys.flags.no_user_site:
        sys.stderr.write("OPERATOR_PREFLIGHT_ISOLATED_PYTHON_REQUIRED\n")
        sys.exit(1)
    if sys.path:
        del sys.path[0]
    sys.path[:] = [entry for entry in sys.path if entry]
import os
import stat
import hashlib


def chain(path):
    while True:
        info = os.lstat(path)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()) or
                info.st_mode & 18):
            raise ValueError("preflight_directory_trust")
        parent = os.path.dirname(path)
        if parent == path:
            return
        path = parent


def binding(path, fd, code=False):
    before, named = os.fstat(fd), os.lstat(path)
    keys = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size")
    if code:
        keys += ("st_mtime", "st_ctime")
    if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or
            before.st_mode & 18 or before.st_nlink != 1 or
            any(getattr(before, key) != getattr(named, key) for key in keys)):
        raise ValueError("preflight_file_binding")
    return tuple(getattr(before, key) for key in keys)


def run(root, expected, launcher_sha256, nonce):
    if os.name != "posix" or not os.path.isabs(root) or os.path.realpath(root) != root:
        raise ValueError("preflight_root")
    for value, length in ((expected, 64), (launcher_sha256, 64), (nonce, 32)):
        if len(value) != length or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("preflight_binding")
    chain(root)
    import fcntl

    lock = root + "/run.lock"
    fd = os.open(lock, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        held = binding(lock, fd)
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        if binding(lock, fd) != held:
            raise ValueError("preflight_lock_drift")
        launcher = root + "/bin/cadence-operator-runner"
        chain(os.path.dirname(launcher))
        code_fd = os.open(launcher, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            before = binding(launcher, code_fd, True)
            if stat.S_IMODE(os.fstat(code_fd).st_mode) != 448:
                raise ValueError("preflight_launcher_permissions")
            source = os.read(code_fd, 262145)
            if (len(source) > 262144 or hashlib.sha256(source).hexdigest() != launcher_sha256 or
                    binding(launcher, code_fd, True) != before):
                raise ValueError("preflight_launcher_binding")
            # The package hash authenticates exactly the bytes compiled here.
            # No interpreter-loaded mutable A can authenticate path B instead.
            namespace = {"__name__": "bound_operator_launcher", "__package__": "",
                         "__file__": launcher}
            eval(compile(source, launcher, "exec"), namespace)
            old = sys.argv
            try:
                sys.argv = [launcher, "preflight", expected, nonce]
                result = namespace["main"]()
            finally:
                sys.argv = old
            chain(root)
            if binding(lock, fd) != held or binding(launcher, code_fd, True) != before:
                raise ValueError("preflight_lifetime_drift")
            return result
        finally:
            os.close(code_fd)
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 5:
            raise ValueError("fixed_preflight_arguments")
        sys.exit(run(*sys.argv[1:]))
    except Exception:
        sys.stderr.write("OPERATOR_PREFLIGHT_BINDING_REJECTED\n")
        sys.exit(1)
