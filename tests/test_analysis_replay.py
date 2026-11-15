"""Protocol/resource controls; actual Docker confinement is tested separately in CI."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools.replay_analysis import LIMIT, _capture, _trial, main, prepare, replay_analysis

IMAGE = 'sha256:'+'a'*64
CID = b'b'*64


def inspected_image(**updates):
    image = dict(Id=IMAGE, Os='linux', Config=dict(Volumes=None))
    image.update(updates)
    return json.dumps(image).encode()


def fixture(root):
    data = b'value\n1\n2\n3\n'
    script = b'import json; print(json.dumps({"total": 6}))\n'
    manifest = dict(schema_version='analysis-replay/1.0', image_id=IMAGE, entrypoint='analysis.py',
                    files=[dict(name=name, sha256=hashlib.sha256(raw).hexdigest())
                           for name, raw in [('analysis.py', script), ('data.csv', data)]],
                    reported=dict(total='6'), timeout_seconds=5)
    for name, raw in [('analysis.py', script), ('data.csv', data)]:
        (root/name).write_bytes(raw)
    (root/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


def result(stdout=b'', code=0, issue=None):
    return dict(stdout=stdout, stderr=b'', code=code, issue=issue)


class AnalysisReplayTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.manifest = fixture(self.root)
        self.path = self.root/'manifest.json'
        self.addCleanup(self.directory.cleanup)

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding='utf-8')

    def fake(self, stdout=b'{"total":6}'):
        return patch('tools.replay_analysis._capture', side_effect=[result(inspected_image()),
                     result(CID), result(stdout), result(b'exited 0'), result(), result(),
                     result(CID), result(stdout), result(b'exited 0'), result(), result()])

    def test_preflight_never_contacts_runtime_and_preserves_sources(self):
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        with patch('tools.replay_analysis._capture', side_effect=AssertionError('No execution')):
            report = replay_analysis(self.path)
        self.assertEqual(report['status'], 'NOT_EXECUTED')
        self.assertEqual(report['runs'], [])
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})
        self.assertFalse(report['scientific_validity_verified'])
        with self.assertRaises(ValueError):replay_analysis(self.path, execute='yes')

    def test_strict_manifest_and_source_failures_precede_any_runtime(self):
        mutations = []
        for key, value in [('schema_version','wrong'), ('image_id','python:latest'), ('files',[]),
                           ('entrypoint','undeclared.py'), ('reported',{}), ('reported',{'bad-key':1}),
                           ('reported',{'total':True}), ('timeout_seconds',True), ('timeout_seconds',301),
                           ('atol','-1'), ('rtol','1.01'), ('extra',True)]:
            bad = copy.deepcopy(self.manifest); bad[key] = value; mutations.append(bad)
        for key, value in [('name','../analysis.py'), ('name','a..py'), ('sha256','0'*64)]:
            bad = copy.deepcopy(self.manifest);bad['files'][0][key] = value; mutations.append(bad)
        bad = copy.deepcopy(self.manifest);bad['files'].append(bad['files'][0]);mutations.append(bad)
        bad = copy.deepcopy(self.manifest);bad['entrypoint']='data.csv';mutations.append(bad)
        with patch('tools.replay_analysis._capture', side_effect=AssertionError('No runtime')):
            for bad in mutations:
                with self.subTest(bad=bad),self.assertRaises(ValueError):
                    self.write(bad); replay_analysis(self.path, execute=True)
        self.write(self.manifest)
        (self.root/'data.csv').write_bytes(b'changed')
        with self.assertRaises(ValueError):prepare(self.path)

    def test_missing_runtime_and_pinned_image_remain_unavailable(self):
        with patch('tools.replay_analysis.shutil.which', return_value=None):
            self.assertEqual(replay_analysis(self.path, True)['status'], 'UNAVAILABLE')
        for inspected in [result(b'wrong'), result(code=1), result(issue='timeout')]:
            with patch('tools.replay_analysis.shutil.which', return_value='docker'), patch('tools.replay_analysis._capture',return_value=inspected):
                self.assertEqual(replay_analysis(self.path, True)['status'], 'UNAVAILABLE')

    def test_inherited_volumes_and_wrong_image_platform_are_rejected(self):
        for metadata in [inspected_image(Config=dict(Volumes={'/extra':{}})),
                         inspected_image(Os='windows'),inspected_image(Id='sha256:'+'b'*64),
                         inspected_image(Config=None)]:
            with patch('tools.replay_analysis.shutil.which',return_value='docker'),patch('tools.replay_analysis._capture',return_value=result(metadata)) as capture:
                report=replay_analysis(self.path,True)
                self.assertEqual(report['status'],'UNAVAILABLE')
                self.assertEqual(capture.call_count,1)

    def test_staging_access_is_independent_of_private_caller_umask(self):
        import os
        with patch('tools.replay_analysis.shutil.which',return_value='docker'),patch('tools.replay_analysis._capture',return_value=result(inspected_image())),patch('tools.replay_analysis._trial') as trial:
            def check(docker, folder, prepared):
                if os.name!='nt':
                    self.assertEqual(folder.stat().st_mode & 0o777,0o755)
                    self.assertEqual(folder.parent.stat().st_mode & 0o777,0o700)
                else:
                    self.assertTrue(folder.is_dir())  # Windows stat is not a POSIX ACL check.
                return dict(code=0,stdout=b'{"total":6}',stderr=b'',issue=None,cleanup_confirmed=True,container_name='synthetic')
            trial.side_effect=check
            old=os.umask(0o077)
            try:report=replay_analysis(self.path,True)
            finally:os.umask(old)
        self.assertEqual(report['status'],'VERIFIED')

    def test_two_trials_exact_numeric_comparison_and_local_resource_flags(self):
        with patch('tools.replay_analysis.shutil.which', return_value='docker'),self.fake() as capture:
            report = replay_analysis(self.path, True)
        self.assertEqual(report['status'], 'VERIFIED')
        self.assertTrue(report['repeatable_selected_values'])
        self.assertTrue(report['cleanup_confirmed'])
        commands = [call.args[0] for call in capture.call_args_list]
        runs = [command for command in commands if 'create' in command]
        self.assertEqual(len(runs),2)
        for command in runs:
            self.assertEqual(command[command.index('--network')+1], 'none')
            self.assertEqual(command[command.index('--pull')+1], 'never')
            self.assertEqual(command[command.index('--user')+1], '65534:65534')
            self.assertEqual(command[command.index('--entrypoint')+1], 'python')
            self.assertIn('--read-only',command)
            self.assertIn('--no-healthcheck',command)
            self.assertIn('ALL',command)
            self.assertIn('512m',command)
            self.assertIn('no-new-privileges:true',command)
            self.assertTrue(command[command.index('--mount')+1].endswith(',dst=/inputs,readonly'))
            self.assertIn(IMAGE,command)
            self.assertIn('-I',command)
        self.assertFalse(report['deterministic_execution_guaranteed'])

    def test_refutation_tolerance_and_large_exact_numbers(self):
        with patch('tools.replay_analysis.shutil.which', return_value='docker'),self.fake(b'{"total":7}'):
            self.assertEqual(replay_analysis(self.path, True)['status'],'REFUTED')
        self.manifest['atol'] = '.1';self.write(self.manifest)
        with patch('tools.replay_analysis.shutil.which', return_value='docker'),self.fake(b'{"total":6.1}'):
            self.assertEqual(replay_analysis(self.path, True)['status'],'VERIFIED')
        self.manifest['reported']['total']='9007199254740993.0';self.write(self.manifest)
        with patch('tools.replay_analysis.shutil.which', return_value='docker'),self.fake(b'{"total":9007199254740992.0}'):
            self.assertEqual(replay_analysis(self.path, True)['status'],'REFUTED')

    def test_nonrepeatable_outputs_abstain(self):
        responses = [result(inspected_image()),result(CID),result(b'{"total":6}'),result(b'exited 0'),result(),result(),
                     result(CID),result(b'{"total":7}'),result(b'exited 0'),result(),result()]
        with patch('tools.replay_analysis.shutil.which', return_value='docker'),patch('tools.replay_analysis._capture',side_effect=responses):
            report = replay_analysis(self.path, True)
        self.assertEqual(report['status'],'UNDETERMINED')
        self.assertFalse(report['repeatable_selected_values'])
        self.assertEqual(report['execution_status'],'partial')

    def test_cleanup_or_process_failure_cannot_create_agreement(self):
        for trial, cleanup in [(result(b'{"total":6}',code=1),result()),
                               (result(issue='timeout'),result()),
                               (result(issue='output_limit'),result()),
                               (result(b'{"total":6}'),result(b'sra-replay-fixed\n')),
                               (result(b'{"total":6}'),result(code=1))]:
            responses=[result(inspected_image()),result(CID),trial]
            if trial['code']==0 and trial['issue'] is None:
                responses.append(result(b'exited 0'))
            responses.extend([result(),cleanup])
            with self.subTest(trial=trial,cleanup=cleanup),patch('tools.replay_analysis.shutil.which',return_value='docker'),patch('tools.replay_analysis._capture',side_effect=responses),patch('tools.replay_analysis.uuid.uuid4',return_value=SimpleNamespace(hex='fixed')):
                self.assertEqual(replay_analysis(self.path,True)['status'],'FAILED')

    def test_bad_output_keys_nonfinite_duplicate_and_text_fail_closed(self):
        for raw in [b'not-json',b'{"other":6}',b'{"total":true}',b'{"total":NaN}',
                    b'{"total":6,"total":6}',b'{"total":"1e9999"}',b'\xff']:
            with self.subTest(raw=raw),patch('tools.replay_analysis.shutil.which',return_value='docker'),self.fake(raw):
                report=replay_analysis(self.path,True)
                self.assertEqual(report['status'],'FAILED')
                self.assertTrue(report['cleanup_confirmed'])

    def test_runtime_exception_still_attempts_removal(self):
        responses=[result(inspected_image()),OSError('simulated launch failure'),result(),result()]
        with patch('tools.replay_analysis.shutil.which',return_value='docker'),patch('tools.replay_analysis._capture',side_effect=responses) as capture:
            report=replay_analysis(self.path,True)
        self.assertEqual(report['status'],'FAILED')
        self.assertFalse(report['cleanup_confirmed'])
        self.assertTrue(any('rm' in call.args[0] for call in capture.call_args_list))

    def test_unconfirmed_creation_exit_state_and_cleanup_fail_closed(self):
        responses = [result(inspected_image()),result(b'invalid-id'),result(),result()]
        with patch('tools.replay_analysis.shutil.which',return_value='docker'),patch('tools.replay_analysis._capture',side_effect=responses) as capture:
            report=replay_analysis(self.path,True)
        self.assertEqual(report['status'],'FAILED')
        self.assertFalse(report['cleanup_confirmed'])
        self.assertFalse(any('start' in call.args[0] for call in capture.call_args_list))
        for state in [result(b'running 0'),result(b'exited 7'),result(code=1)]:
            responses = [result(inspected_image()),result(CID),result(b'{"total":6}'),state,result(),result()]
            with patch('tools.replay_analysis.shutil.which',return_value='docker'),patch('tools.replay_analysis._capture',side_effect=responses):
                report=replay_analysis(self.path,True)
                self.assertEqual(report['status'],'FAILED')
                self.assertTrue(report['cleanup_confirmed'])
        responses = [result(inspected_image()),result(CID),result(b'{"total":6}'),result(b'exited 0'),OSError('cleanup unavailable')]
        with patch('tools.replay_analysis.shutil.which',return_value='docker'),patch('tools.replay_analysis._capture',side_effect=responses):
            report=replay_analysis(self.path,True)
        self.assertEqual(report['status'],'FAILED')
        self.assertFalse(report['cleanup_confirmed'])
        self.assertTrue(report['runs'][0]['container_name'].startswith('sra-replay-'))

    def test_oversized_and_symlink_sources_are_rejected(self):
        with patch('tools.replay_analysis.MAX_INPUT',5):
            with self.assertRaises(ValueError):prepare(self.path)
        self.write({**self.manifest,'files':self.manifest['files']*17})
        with self.assertRaises(ValueError):prepare(self.path)
        self.write(self.manifest)
        data=self.root/'data.csv';backup=self.root/'backup.csv';data.rename(backup)
        try:
            data.symlink_to(backup)
        except OSError:
            # Native Windows may not grant symlink privileges; exercise the same
            # preflight result without pretending a link was created there.
            with patch('tools.replay_analysis.Path.is_symlink',return_value=True):
                with self.assertRaises(ValueError):prepare(self.path)
        else:
            with self.assertRaises(ValueError):prepare(self.path)

    def test_cli_reserves_output_before_any_execution_and_never_overwrites_sources(self):
        out=self.root/'report.json'
        args=[str(self.path),'--execute','--out',str(out)]
        out.write_text('existing')
        with patch('tools.replay_analysis.replay_analysis',side_effect=AssertionError('No execution')):
            with self.assertRaises(FileExistsError):main(args)
            with self.assertRaises(FileExistsError):main([str(self.path),'--execute','--out',str(self.root/'data.csv')])
        out.unlink()
        with patch('tools.replay_analysis.replay_analysis',side_effect=ValueError('bad')):
            with self.assertRaises(ValueError):main(args)
        self.assertFalse(out.exists())
        self.assertEqual(main([str(self.path),'--out',str(out)]),0)
        self.assertEqual(json.loads(out.read_text())['status'],'NOT_EXECUTED')

    def test_real_capture_normal_timeout_and_output_bound(self):
        ok=_capture([sys.executable,'-I','-c','print("ok")'],5)
        self.assertEqual(ok['stdout'].strip(),b'ok')
        self.assertIsNone(ok['issue'])
        timeout=_capture([sys.executable,'-I','-c','import time;time.sleep(2)'],.05)
        self.assertEqual(timeout['issue'],'timeout')
        large=_capture([sys.executable,'-I','-c','import sys;sys.stdout.write("x"*200000);sys.stdout.flush()'],5)
        self.assertEqual(large['issue'],'output_limit')
        self.assertLessEqual(len(large['stdout'])+len(large['stderr']),LIMIT)

    def test_capture_exception_does_not_leave_its_client_process_running(self):
        original=subprocess.Popen
        children=[]
        def spawn(*args,**kwargs):
            child=original(*args,**kwargs);children.append(child);return child
        with patch('tools.replay_analysis.subprocess.Popen',side_effect=spawn),patch('tools.replay_analysis._drain',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                _capture([sys.executable,'-I','-c','import time;time.sleep(10)'],5)
        self.assertEqual(len(children),1)
        self.assertIsNotNone(children[0].poll())
        children[0].stdout.close();children[0].stderr.close()


if __name__ == '__main__':
    unittest.main()
