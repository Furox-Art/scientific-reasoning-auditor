"""Explicit offline Python analysis replay in a pinned local Docker image.

No host-execution fallback, automatic image download, or manuscript/MCP execution.
The Docker daemon, image and host configuration remain trusted prerequisites.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from fractions import Fraction

from sra.error_benchmark import bounded_json, fingerprint
from sra.json_utils import canonical_json
from sra.toolkit_spec import _fields, _NAME, number

LIMIT = 65536
MAX_INPUT = 16*1024*1024
FILE_NAME = re.compile(r'[A-Za-z][A-Za-z0-9_.-]{0,63}\Z')
IMAGE = re.compile(r'sha256:[0-9a-f]{64}\Z')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _value(value, tolerance=False):
    value = str(number(value))
    if tolerance and not 0 <= Fraction(value) <= 1:
        raise ValueError('Replay tolerances must be in [0,1].')
    return value


def prepare(path):
    path = Path(path)
    with path.open('rb') as stream:
        raw = stream.read(1024*1024+1)
    manifest = bounded_json(raw.decode('utf-8'))
    _fields(manifest, ('schema_version', 'image_id', 'entrypoint', 'files', 'reported'),
            ('atol', 'rtol', 'timeout_seconds'))
    if manifest['schema_version'] != 'analysis-replay/1.0' or not isinstance(manifest['image_id'], str) or not IMAGE.fullmatch(manifest['image_id']):
        raise ValueError('Declare schema analysis-replay/1.0 and a content-addressed local image ID.')
    files = manifest['files']
    if not isinstance(files, list) or not 1 <= len(files) <= 16:
        raise ValueError('Declare 1..16 exact input files.')
    assets, total = {}, 0
    for row in files:
        _fields(row, ('name', 'sha256'))
        name = row['name']
        if (not isinstance(name, str) or not FILE_NAME.fullmatch(name) or '..' in name or
                name in assets or not isinstance(row['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', row['sha256'])):
            raise ValueError('Input names must be distinct safe basenames with SHA256 digests.')
        source = path.parent/name
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_INPUT-total:
            raise ValueError('Inputs must be regular non-symlink files totaling at most 16 MiB.')
        with source.open('rb') as stream:
            content = stream.read(MAX_INPUT-total+1)
        total += len(content)
        if total > MAX_INPUT or _sha(content) != row['sha256']:
            raise ValueError('Input bytes differ from the declared source snapshot.')
        assets[name] = content
    entrypoint = manifest['entrypoint']
    if not isinstance(entrypoint, str) or entrypoint not in assets or not entrypoint.endswith('.py'):
        raise ValueError('entrypoint must name one declared Python file.')
    reported = manifest['reported']
    if (not isinstance(reported, dict) or not 1 <= len(reported) <= 32 or
            any(not _NAME.fullmatch(key) for key in reported)):
        raise ValueError('Declare 1..32 numeric reported results with simple keys.')
    expected = {key: _value(value) for key, value in reported.items()}
    timeout = manifest.get('timeout_seconds', 60)
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise ValueError('timeout_seconds must be an integer in [1,300].')
    return dict(manifest=manifest, manifest_sha256=fingerprint(manifest), assets=assets,
                expected=expected, entrypoint=entrypoint, image=manifest['image_id'], timeout=timeout,
                atol=_value(manifest.get('atol', '0'), True), rtol=_value(manifest.get('rtol', '0'), True))


def _capture(command, timeout):
    """Bound aggregate stdout/stderr in memory; never invoke a shell."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('DOCKER_')}
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=env)
    try:
        return _drain(process, timeout)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def _drain(process, timeout):
    buffers, size, capture_errors, stop, lock = [bytearray(), bytearray()], [0], [False], threading.Event(), threading.Lock()
    def read(stream, index):
        try:
            with stream:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    with lock:
                        room = max(0, LIMIT-size[0])
                        buffers[index].extend(chunk[:room])
                        size[0] += len(chunk)
                        if size[0] > LIMIT:
                            stop.set()
                            break
        except OSError:
            capture_errors[0] = True
            stop.set()
    threads = [threading.Thread(target=read, args=(stream, i), daemon=True)
               for i, stream in enumerate((process.stdout, process.stderr))]
    for thread in threads:
        thread.start()
    deadline, issue = time.monotonic()+timeout, None
    while process.poll() is None:
        if stop.wait(.02):
            issue = 'output_limit'
            break
        if time.monotonic() >= deadline:
            issue = 'timeout'
            break
    if issue:
        process.kill()
    process.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=1)
    if stop.is_set():
        issue = 'output_limit'
    if any(thread.is_alive() for thread in threads):
        issue = 'capture_incomplete'
    if capture_errors[0]:
        issue = 'capture_failed'
    return dict(code=process.returncode, stdout=bytes(buffers[0]), stderr=bytes(buffers[1]), issue=issue)


def _ok(result):
    return result['code'] == 0 and result['issue'] is None


def _trial(docker, folder, prepared):
    name = 'sra-replay-'+uuid.uuid4().hex
    mount = str(folder.resolve())
    if ',' in mount:
        raise ValueError('The temporary staging path must not contain commas.')
    command = [*docker, 'create', '--name', name, '--pull', 'never',
               '--network', 'none', '--ipc', 'none', '--read-only', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges:true', '--user', '65534:65534',
               '--pids-limit', '64', '--memory', '512m', '--memory-swap', '512m', '--cpus', '1',
               '--log-driver', 'none', '--workdir', '/inputs',
               '--no-healthcheck',
               '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
               '--mount', 'type=bind,src='+mount+',dst=/inputs,readonly',
               '--env', 'OPENBLAS_NUM_THREADS=1', '--env', 'OMP_NUM_THREADS=1',
               '--env', 'MKL_NUM_THREADS=1', '--env', 'NUMEXPR_NUM_THREADS=1',
               '--entrypoint', 'python', prepared['image'], '-I', '-B', '/inputs/'+prepared['entrypoint']]
    result = dict(code=None, stdout=b'', stderr=b'', issue='launch_or_control_failure')
    cleanup, creation_confirmed = False, False
    try:
        try:
            created = _capture(command, 10)
            creation_confirmed = _ok(created) and bool(re.fullmatch(rb'[0-9a-f]{64}', created['stdout'].strip()))
            if creation_confirmed:
                result = _capture([*docker, 'start', '--attach', name], prepared['timeout'])
                if _ok(result):
                    state = _capture([*docker, 'inspect', '--format', '{{.State.Status}} {{.State.ExitCode}}', name], 10)
                    matched = re.fullmatch(rb'exited ([0-9]{1,3})', state['stdout'].strip()) if _ok(state) else None
                    if matched:
                        result['code'] = int(matched[1])
                    else:
                        result['issue'] = 'container_exit_state_unconfirmed'
            else:
                result.update(issue='container_creation_unconfirmed', stderr=created['stderr'])
        except (OSError, subprocess.SubprocessError):
            pass
    finally:
        # Killing the attached Docker client does not prove container termination.
        # Explicitly remove only our random-name container and verify its absence.
        try:
            _capture([*docker, 'rm', '--force', '--volumes', name], 10)
            # Exact membership in an unfiltered successful name inventory avoids
            # mistaking a malformed/filter-mismatched query for verified absence.
            remaining = _capture([*docker, 'ps', '-a', '--format', '{{.Names}}'], 10)
            cleanup = creation_confirmed and _ok(remaining) and name.encode('ascii') not in remaining['stdout'].splitlines()
        except (OSError, subprocess.SubprocessError):
            pass
    result.update(cleanup_confirmed=cleanup, container_name=name)
    return result


def replay_analysis(path, execute=False):
    """Preflight by default; execution requires explicit caller opt-in."""
    if type(execute) is not bool:
        raise ValueError('execute must be an explicit boolean.')
    prepared = prepare(path)
    report = dict(schema_version='analysis-replay-result/1.0', adapter_version='analysis-replay/1.0',
                  adapter_source_sha256=_sha(Path(__file__).read_bytes()), manifest_sha256=prepared['manifest_sha256'],
                  image_id=prepared['image'], input_sha256={k: _sha(v) for k, v in prepared['assets'].items()},
                  execution_status='not_executed', status='NOT_EXECUTED', runs=[],
                  source_access='read_only_staged_copies', network_policy='none',
                  reported_values=prepared['expected'], atol=prepared['atol'], rtol=prepared['rtol'],
                  repeatable_selected_values=None, scientific_validity_verified=False,
                  cleanup_confirmed=None,
                  isolation_certified=False, deterministic_execution_guaranteed=False,
                  limitations=['Only declared numeric outputs are compared; source authenticity, prose mapping and analysis adequacy are unverified.',
                               'Two matching runs do not prove general determinism; script seeds, dependencies and model assumptions remain caller responsibilities.',
                               'A trusted local Linux-container Docker daemon/image/host is required. Container flags are not a security certification.'])
    if not execute:
        return report
    report.update(execution_status='partial', status='UNAVAILABLE')
    executable = shutil.which('docker')
    if executable is None:
        report['reason'] = 'local_docker_client_unavailable'
        return report
    # Explicit local endpoints prevent DOCKER_HOST/context from selecting a remote
    # daemon and exposing staged data to it. Rootless/custom endpoints are outside
    # this bounded adapter; there is no weaker host-process fallback.
    endpoint = 'npipe:////./pipe/docker_engine' if os.name == 'nt' else 'unix:///var/run/docker.sock'
    docker = [executable, '--host', endpoint]
    try:
        inspected = _capture([*docker, 'image', 'inspect', prepared['image'], '--format', '{{json .}}'], 10)
        if not _ok(inspected):
            report['reason'] = 'pinned_local_image_or_daemon_unavailable'
            return report
        try:
            image = bounded_json(inspected['stdout'].decode('utf-8'))
        except (ValueError, UnicodeError):
            report['reason'] = 'local_image_metadata_invalid'
            return report
        if image.get('Id') != prepared['image'] or image.get('Os') != 'linux' or not isinstance(image.get('Config'), dict):
            report['reason'] = 'pinned_linux_image_metadata_mismatch'
            return report
        if image['Config'].get('Volumes') not in (None, {}):
            report['reason'] = 'image_declares_unsupported_volumes'
            return report
        with tempfile.TemporaryDirectory(prefix='sra-replay-') as directory:
            # Keep the host parent private (0700). Bind only its readable child
            # so a nonroot container can read the explicitly staged copies.
            folder = Path(directory)/'inputs'
            folder.mkdir(mode=0o755)
            folder.chmod(0o755)  # mkdir's mode alone is filtered by caller umask.
            for name, content in prepared['assets'].items():
                target = folder/name
                target.write_bytes(content)
                target.chmod(0o644)
            report['status'] = 'FAILED'
            for _ in range(2):
                report['cleanup_confirmed'] = False
                result = _trial(docker, folder, prepared)
                report['cleanup_confirmed'] = result['cleanup_confirmed']
                record = dict(exit_code=result['code'], issue=result['issue'],
                              container_name=result['container_name'],
                              stdout_sha256=_sha(result['stdout']), stderr_sha256=_sha(result['stderr']),
                              cleanup_confirmed=result['cleanup_confirmed'])
                report['runs'].append(record)
                if not _ok(result) or not result['cleanup_confirmed']:
                    report['reason'] = 'execution_or_cleanup_incomplete'
                    return report
                values = bounded_json(result['stdout'].decode('utf-8'))
                if set(values) != set(prepared['expected']):
                    raise ValueError('Executed output keys must match the declared numeric results.')
                record['values'] = {key: _value(value) for key, value in values.items()}
        left, right = [r['values'] for r in report['runs']]
        report['repeatable_selected_values'] = all(Fraction(left[k]) == Fraction(right[k]) for k in left)
        if not report['repeatable_selected_values']:
            report.update(status='UNDETERMINED', reason='selected_outputs_differ_between_runs')
            return report
        report['comparisons'] = [dict(name=k, computed=left[k], reported=v,
            agrees=abs(Fraction(left[k])-Fraction(v)) <= Fraction(prepared['atol'])+Fraction(prepared['rtol'])*abs(Fraction(v)))
            for k, v in prepared['expected'].items()]
        report.update(execution_status='complete', status='VERIFIED' if all(r['agrees'] for r in report['comparisons']) else 'REFUTED')
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        report.update(status='FAILED', reason='replay_protocol_or_runtime_failure')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--execute', action='store_true', help='Explicitly run two isolated local-container trials.')
    parser.add_argument('--out', required=True, type=Path, help='New JSON report; existing files are never overwritten.')
    args = parser.parse_args(argv)
    # Reserve before any possible execution; aliases of an input cannot be opened.
    with args.out.open('xb') as stream:
        try:
            report = replay_analysis(args.manifest, execute=args.execute)
            stream.write((canonical_json(report)+'\n').encode('utf-8'))
        except BaseException:
            stream.close()
            args.out.unlink()
            raise
    print(f"Analysis replay: {report['status']}; no scientific validity verdict.")
    return 0 if report['status'] in ('NOT_EXECUTED', 'VERIFIED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
