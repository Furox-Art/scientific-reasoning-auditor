"""Actual synthetic Docker integration, including resource/permission failure paths."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from replay_analysis import replay_analysis


def verify(image_id):
    with tempfile.TemporaryDirectory(prefix='sra-real-replay-') as directory:
        root = Path(directory)
        script = '''import csv, json, os, socket
from pathlib import Path
with open('/inputs/data.csv') as stream:
    total = sum(int(row['value']) for row in csv.DictReader(stream))
def denied(path):
    try:
        with open(path, 'w') as stream:
            stream.write('unexpected')
        return 0
    except OSError:
        return 1
with open('/proc/mounts') as stream:
    mount_flags = {parts[1]: parts[3].split(',') for parts in (line.split() for line in stream)}
try:
    with socket.create_connection(('192.0.2.1', 9), timeout=.5):
        blocked = 0
except OSError:
    blocked = 1
print(json.dumps(dict(total=total, input_readonly=denied('/inputs/data.csv'),
    root_readonly=denied('/var/tmp/sra-unexpected-write'), nonroot=int(os.getuid()!=0),
    input_mount_readonly=int('ro' in mount_flags['/inputs']),
    root_mount_readonly=int('ro' in mount_flags['/']),
    network_blocked=blocked)))
'''
        (root/'analysis.py').write_text(script, encoding='utf-8')
        (root/'data.csv').write_bytes(b'value\n1\n2\n3\n')
        original = {p.name:p.read_bytes() for p in root.iterdir()}
        manifest = dict(schema_version='analysis-replay/1.0', image_id=image_id,
                        entrypoint='analysis.py', timeout_seconds=30,
                        files=[dict(name=name,sha256=hashlib.sha256(raw).hexdigest()) for name,raw in original.items()],
                        reported=dict(total=6,input_readonly=1,root_readonly=1,nonroot=1,network_blocked=1,
                                      input_mount_readonly=1,root_mount_readonly=1))
        path = root/'manifest.json'
        path.write_text(json.dumps(manifest),encoding='utf-8')
        first = replay_analysis(path, execute=True)
        assert first['status']=='VERIFIED',first
        assert first['repeatable_selected_values'] and first['cleanup_confirmed'],first
        assert original == {name:(root/name).read_bytes() for name in original}
        manifest['reported']['total'] = 7
        path.write_text(json.dumps(manifest),encoding='utf-8')
        mismatch = replay_analysis(path,execute=True)
        assert mismatch['status']=='REFUTED' and mismatch['cleanup_confirmed'],mismatch
        for content,timeout,issue in [('import time; time.sleep(10)\n',1,'timeout'),
                                      ('print("x"*200000)\n',30,'output_limit')]:
            (root/'analysis.py').write_text(content,encoding='utf-8')
            next(row for row in manifest['files'] if row['name']=='analysis.py')['sha256']=hashlib.sha256((root/'analysis.py').read_bytes()).hexdigest()
            manifest['timeout_seconds']=timeout
            path.write_text(json.dumps(manifest),encoding='utf-8')
            failed = replay_analysis(path,execute=True)
            assert failed['status']=='FAILED' and failed['cleanup_confirmed'],failed
            assert failed['runs'][0]['issue']==issue,failed
        (root/'data.csv').write_bytes(b'changed after freeze')
        try:
            replay_analysis(path,execute=True)
        except ValueError:
            pass
        else:
            raise AssertionError('Changed input was accepted')
        print(json.dumps(dict(actual_container_replay=True,image_id=image_id,
                              readonly_inputs=True,readonly_root=True,nonroot=True,network_blocked=True,
                              two_run_agreement=True,reported_mismatch_detected=True,
                              timeout_and_output_limit_cleanup=True,source_change_rejected=True)))


if __name__=='__main__':
    verify(sys.argv[1])
