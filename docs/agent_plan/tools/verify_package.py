#!/usr/bin/env python3
"""Verify the downloaded documentation package using Python's standard library.

Reads files only. Does not install packages, access networks, invoke subprocesses,
change Git state, or contact Cadence. Integrity hashes are not signatures/approvals.
"""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    with path.open('r', encoding='utf-8') as handle:
        return json.load(handle)


def relative_target(root, name):
    parts = PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts or '\\' in name:
        raise ValueError('unsafe manifest path: ' + name)
    target = root.joinpath(*parts.parts)
    if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != root.parent):
        raise ValueError('symlink is not a package file: ' + name)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError('path escaped root: ' + name) from None
    return target


def markdown_visible(text):
    fence = None
    visible = []
    for line in text.splitlines():
        match = re.match(r'^\s*(`{3,}|~{3,})(.*)$', line)
        if match:
            token, tail = match.groups()
            if fence is None:
                fence = (token[0], len(token))
            elif token[0] == fence[0] and len(token) >= fence[1] and not tail.strip():
                fence = None
            continue
        if fence is None:
            visible.append(line)
    return '\n'.join(visible), fence is None


def validate(root):
    errors = []
    checks = []
    manifest = read_json(root / 'PACKAGE_MANIFEST.json')
    entries = manifest['files']
    names = [e['path'] for e in entries]
    if len(names) != len(set(names)):
        errors.append('duplicate paths in manifest')
    for entry in entries:
        path = relative_target(root, entry['path'])
        if not path.is_file():
            errors.append('missing: ' + entry['path'])
            continue
        data = path.read_bytes()
        if len(data) != entry['bytes'] or digest(data) != entry['sha256']:
            errors.append('hash/size mismatch: ' + entry['path'])
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    expected = set(names) | {'PACKAGE_MANIFEST.json', 'CHECKSUMS.sha256'}
    extra = actual - expected
    if extra:
        errors.append('unexpected files in original package: ' + ', '.join(sorted(extra)))
    checks.append(f'file manifest: {len(entries)} entries')

    expected_checksums = {}
    for line in (root / 'CHECKSUMS.sha256').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        sha, name = line.split('  ', 1)
        if name in expected_checksums:
            errors.append('duplicate checksum entry: ' + name)
        expected_checksums[name] = sha
        path = relative_target(root, name)
        if not path.is_file() or digest(path.read_bytes()) != sha:
            errors.append('checksum mismatch: ' + name)
    if set(expected_checksums) != set(names) | {'PACKAGE_MANIFEST.json'}:
        errors.append('checksum coverage mismatch')
    checks.append('checksum coverage')

    catalog = read_json(root / 'planning/work_packages.json')
    tasks = [t for phase in catalog['phases'] for t in phase['tasks']]
    ids = [t['id'] for t in tasks]
    by_id = {t['id']: t for t in tasks}
    if len(catalog['phases']) != 16 or len(tasks) != 120 or len(ids) != len(set(ids)):
        errors.append('task/phase count or uniqueness mismatch')
    for task in tasks:
        if task.get('authorization_granted') is not False:
            errors.append('task contains implicit execution authority: ' + task['id'])
        if not relative_target(root, task['prompt_path']).is_file():
            errors.append('missing prompt: ' + task['id'])
        for dep in task['dependencies']:
            if dep not in by_id:
                errors.append('unknown dependency: ' + dep)
    visiting, done = set(), set()
    def visit(task_id):
        if task_id in visiting:
            raise ValueError('dependency cycle at ' + task_id)
        if task_id in done:
            return
        visiting.add(task_id)
        for dep in by_id[task_id]['dependencies']:
            if dep in by_id:
                visit(dep)
        visiting.remove(task_id)
        done.add(task_id)
    for task_id in by_id:
        visit(task_id)
    checks.append('16 phases / 120 task IDs / dependency DAG')

    legacy = read_json(root / 'planning/legacy_capabilities.json')['entries']
    if len(legacy) != 170 or len({e['legacy_id'] for e in legacy}) != 170:
        errors.append('original capability coverage is not 170')
    for item in legacy:
        if not item['integrated_task_ids'] or any(
            value not in by_id for value in item['integrated_task_ids']
        ):
            errors.append('unmapped legacy capability: ' + item['legacy_id'])
    hardening = read_json(root / 'planning/hardening_requirements.json')['requirements']
    if {x['id'] for x in hardening} != {f'R{i:02d}' for i in range(1, 22)}:
        errors.append('hardening requirement IDs are incomplete')
    for item in hardening:
        if any(v not in by_id for v in item['task_ids']):
            errors.append('unknown hardening task mapping: ' + item['id'])
        if not relative_target(root, item['contract']).is_file():
            errors.append('missing hardening contract: ' + item['id'])
    checks.append('170 original capabilities / 21 hardening requirements mapped')

    template_count = 0
    for path in (root / 'templates').glob('*.json'):
        data = read_json(path)
        template_count += 1
        if data.get('is_template') is not True or data.get('execution_authorized') is not False:
            errors.append('template can be mistaken for authorization: ' + path.name)
        if 'enabled' in data and data['enabled'] is not False:
            errors.append('template enabled: ' + path.name)
    checks.append(f'{template_count} inactive JSON templates')

    markdown_files = list(root.rglob('*.md'))
    for path in markdown_files:
        text = path.read_text(encoding='utf-8')
        visible, fences_ok = markdown_visible(text)
        if not fences_ok:
            errors.append('unclosed Markdown fence: ' + path.relative_to(root).as_posix())
        for target in re.findall(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)', visible):
            if target.startswith(('http:', 'https:', 'mailto:', '#')):
                continue
            target = target.strip('<>')
            target_path = unquote(urlsplit(target).path)
            if not target_path:
                continue
            resolved = (path.parent / target_path).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                errors.append('Markdown link escapes package: ' + target)
                continue
            if not resolved.exists():
                errors.append(f'broken link in {path.relative_to(root)}: {target}')
    checks.append(
        f'{len(markdown_files)} UTF-8 Markdown files / fences / local links'
    )

    sources = read_json(root / 'planning/recovered_sources.json')['records']
    with zipfile.ZipFile(root / 'archive/LEGACY_INPUTS.zip', 'r') as archive:
        if archive.testzip() is not None:
            errors.append('legacy archive CRC failed')
        for name in archive.namelist():
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name:
                errors.append('unsafe archive member: ' + name)
        for source in sources:
            data = archive.read(source['archive_path'])
            if digest(data) != source['sha256'] or len(data) != source['bytes']:
                errors.append('recovered original mismatch: ' + source['archive_path'])
    checks.append(
        f'{len(sources)} recovered original files byte-preserved in historical archive'
    )
    return checks, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        checks, errors = validate(args.root.resolve())
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        print(f'PACKAGE CHECK FAILED: {exc}', file=sys.stderr)
        return 1
    for check in checks:
        print('CHECK: ' + check)
    if errors:
        for error in errors:
            print('FAIL: ' + error, file=sys.stderr)
        return 1
    print('PASS: documentation package integrity and consistency verified.')
    print('NOT RUN: repository tests, SSH, Cadence, EDA safety validation, or design signoff.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
