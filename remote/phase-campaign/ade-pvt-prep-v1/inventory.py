#!/usr/bin/env python
"""Fixed protected PDK inventory. Python 2.6; never exports model statements."""
from __future__ import with_statement

import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = "/home/buet/cds_work/.cadence_mcp"
VERSION = ROOT + "/phase-campaign/ade-pvt-prep-v1"
RUNTIME = ROOT + "/ade-pvt-prep-v1"
MODELS = "/home/buet/cadence/gpdk090_v4.6/models/spectre"
MAIN = MODELS + "/gpdk090.scs"
MAX_BYTES = 32 * 1024 * 1024
TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.$-]{0,95}$")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def clean(text):
    # Keep quoted include targets intact; strip comments without finding false sections.
    pattern = r'"(?:[^"\\]|\\.)*"|/\*[\s\S]*?\*/|//[^\n]*'
    return re.sub(pattern, lambda match: match.group(0) if match.group(0).startswith('"')
                  else '\n' * match.group(0).count('\n'), text)


def metadata(text):
    text = clean(text)
    library = re.findall(r"(?mi)^\s*library\s+([A-Za-z][A-Za-z0-9_.$-]*)\s*$", text)
    sections = []
    current = None
    outside = []
    for line in text.splitlines():
        begin = re.match(r"^\s*section\s+(\S+)\s*$", line, re.I)
        end = re.match(r"^\s*endsection(?:\s+(\S+))?\s*$", line, re.I)
        if begin:
            name = begin.group(1)
            if current is not None or not TOKEN.match(name) or name in [x[0] for x in sections]:
                raise ValueError("ambiguous model section")
            current = [name, []]
        elif end:
            if current is None or end.group(1) not in (None, current[0]):
                raise ValueError("unbalanced model section")
            sections.append((current[0], '\n'.join(current[1])))
            current = None
        elif current is not None:
            current[1].append(line)
        else:
            outside.append(line)
    if current is not None:
        raise ValueError("unterminated model section")
    if len(library) > 1 or len(sections) > 64:
        raise ValueError("bounded library inventory")
    bodies = [(None, '\n'.join(outside))] + sections
    result = []
    for name, body in bodies:
        includes = []
        for match in re.finditer(r'(?mi)^\s*include\s+"([^"\n]+)"(?:\s+section\s*=\s*([A-Za-z][A-Za-z0-9_.$-]*))?', body):
            includes.append((match.group(1), match.group(2)))
        stats = len(re.findall(r"\bstatistics\s*\{", body, re.I))
        process = len(re.findall(r"\bprocess\s*\{", body, re.I))
        mismatch = len(re.findall(r"\bmismatch\s*\{", body, re.I))
        varying = re.findall(r"\bvary\s+([A-Za-z][A-Za-z0-9_]*)\b", body, re.I)
        # Lexical use is only a prerequisite; it does not prove effective device variation.
        uses = sum(len(re.findall(r"\b" + re.escape(value) + r"\b", body)) > 1
                   for value in set(varying))
        devices = sorted(set(re.findall(r"(?mi)^\s*(?:model|subckt)\s+(nmos1v|pmos1v)\b", body)))
        result.append({"section": name, "includes": includes, "statistics_blocks": stats,
                       "process_blocks": process, "mismatch_blocks": mismatch,
                       "vary_declarations": len(varying), "vary_names_referenced": uses,
                       "observed_device_definitions": devices})
    return {"library_count": len(library), "sections": result}


def files():
    if os.path.realpath(MODELS) != MODELS:
        raise ValueError("model root containment")
    records = {}
    total = 0
    for current, dirs, names in os.walk(MODELS):
        if any(os.path.islink(os.path.join(current, name)) for name in dirs + names):
            raise ValueError("model inventory symlink")
        for name in sorted(names):
            path = os.path.join(current, name)
            if not os.path.isfile(path):
                raise ValueError("model inventory special object")
            if not name.endswith(('.scs', '.mdl')):
                continue
            size = os.stat(path).st_size
            total += size
            if size > 8 * 1024 * 1024 or total > MAX_BYTES or len(records) >= 256:
                raise ValueError("model inventory budget")
            with open(path, 'rb') as stream:
                data = stream.read(8 * 1024 * 1024 + 1)
            records[path] = {"sha256": sha(data), "bytes": len(data),
                             "metadata": metadata(data.decode('latin-1'))}
    if MAIN not in records:
        raise ValueError("bound main model missing")
    return records


def closure(records, start_section):
    pending = [(MAIN, start_section)]
    seen = set()
    aggregate = {"statistics_blocks": 0, "process_blocks": 0, "mismatch_blocks": 0,
                 "vary_declarations": 0, "vary_names_referenced": 0}
    devices = set()
    while pending:
        path, section = pending.pop()
        if (path, section) in seen:
            continue
        seen.add((path, section))
        if path not in records:
            raise ValueError("include outside inventoried model boundary")
        bodies = records[path]['metadata']['sections']
        selected = [body for body in bodies if body['section'] is None or
                    (section is not None and body['section'] == section)]
        if section is not None and not any(body['section'] == section for body in selected):
            raise ValueError("included model section absent")
        if section is None and any(body['section'] is not None for body in bodies):
            raise ValueError("sectioned include without section selection")
        for body in selected:
            for key in aggregate:
                aggregate[key] += body[key]
            devices.update(body['observed_device_definitions'])
            for target, next_section in body['includes']:
                target = os.path.normpath(os.path.join(os.path.dirname(path), target))
                if os.path.realpath(target) != target or not target.startswith(MODELS + '/'):
                    raise ValueError("include containment")
                pending.append((target, next_section))
    aggregate.update({"visited_file_sections": len(seen),
                      "observed_device_definitions": sorted(devices),
                      "effective_variation_verified": False})
    return aggregate


def help_probe():
    # Informational help only: never gives Spectre a netlist or starts a simulation.
    path = RUNTIME + '/montecarlo-help.private.txt'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        process = subprocess.Popen(['/usr/bin/timeout', '20',
            '/home/buet/cadence/MMSIM121/tools/bin/spectre', '-h', 'montecarlo'],
            stdout=stream, stderr=subprocess.STDOUT)
        code = process.wait()
    if os.stat(path).st_size > 262144:
        raise ValueError("help output budget")
    with open(path, 'rb') as stream:
        data = stream.read(262145)
    text = data.decode('latin-1')
    return {"exit_code": code, "bytes": len(data), "sha256": sha(data),
            "montecarlo_mentioned": bool(re.search(r'\bmontecarlo\b', text, re.I)),
            "keywords_present": dict((name, bool(re.search(r'\b' + name + r'\b', text, re.I)))
                for name in ('variations', 'process', 'mismatch', 'seed', 'numruns')),
            "runtime_license_verified": False}


def main():
    if len(sys.argv) != 1:
        raise ValueError("no inventory arguments accepted")
    import imp
    native = imp.load_source('pvt_native_guard', ROOT + '/phase-campaign/native-mcp-v1/helper.py')
    base = native.BASE
    base.environment_preflight()
    before = base.snapshot()
    native.references()
    saved = base.state_facts()
    counter = base.read(base.COUNTER, 1024)
    if json.loads(counter) != {"campaign_id": "AUTO-PHASE-01", "count": 24,
                              "result_reserved_bytes": 2014314496}:
        raise ValueError("preparation budget checkpoint changed")
    if os.path.realpath(RUNTIME) != RUNTIME or os.path.lexists(RUNTIME):
        raise ValueError("inventory replay")
    os.mkdir(RUNTIME, 0o700)
    records = files()
    sections = [body['section'] for body in records[MAIN]['metadata']['sections']
                if body['section'] is not None]
    facts = dict((name, closure(records, name)) for name in sections)
    help_result = help_probe()
    # Installed API callable facts are generated by a fixed read-only OCEAN script.
    fd = os.open(RUNTIME + '/api.private.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        process = subprocess.Popen(['/usr/bin/timeout', '45',
            '/home/buet/cadence/IC615/tools/dfII/bin/ocean', '-nograph', '-nocdsinit',
            '-restore', VERSION + '/api.ocn', '-log', RUNTIME + '/ocean.private.log'],
            cwd=RUNTIME, stdout=stream, stderr=subprocess.STDOUT)
        api_code = process.wait()
    if os.stat(RUNTIME + '/api.private.log').st_size > 262144:
        raise ValueError("API output budget")
    with open(RUNTIME + '/api.private.log', 'rb') as stream:
        api_data = stream.read(262145).decode('latin-1')
    api = dict(re.findall(r'(?m)^MCP_PVT_API\|([A-Za-z0-9_]+)\|(t|nil)\s*$', api_data))
    expected = ('modelFile', 'temp', 'desVar', 'monteCarlo', 'monteRun', 'ocnSetXLMode',
                'ocnxlCorner', 'ocnxlMonteCarloOptions', 'ocnxlRun')
    api_complete = api_code == 0 and set(api) == set(expected)
    after_records = files()
    if records != after_records or before != base.snapshot() or counter != base.read(base.COUNTER, 1024):
        raise ValueError("protected data or budget drift")
    native.references()
    result = {"phase": "ADE-PVT-PREP-01", "model_sha256": records[MAIN]['sha256'],
              "model_file_count": len(records), "model_bytes_scanned": sum(x['bytes'] for x in records.values()),
              "sections": facts, "saved_state": saved, "spectre_montecarlo_help": help_result,
              "ocean_api": {"exit_code": api_code, "complete": api_complete,
                            "callable": dict((name, api.get(name) == 't') for name in expected)},
              "protected_unchanged": True, "counter": json.loads(counter),
              "new_circuit_runs": 0, "spec_evaluation": "not_evaluated"}
    base.save(RUNTIME + '/result.json', result)
    base.emit(result)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, IOError):
        sys.stderr.write('fixed PVT preparation failed; preserve private checkpoint\n')
        sys.exit(69)
