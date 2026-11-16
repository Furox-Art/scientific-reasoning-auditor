"""Numerical-reference reports preserve inputs, expectations and every case."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import evaluate_statistical_context as ref


class StatisticalContextReportTests(unittest.TestCase):
    def test_complete_report_and_report_identity(self):
        report=ref.compare()
        self.assertEqual(report['comparison_status'],'MATCHED')
        self.assertEqual(report['actual_status_counts'],{'REFUTED':2,'UNDETERMINED':6,'VERIFIED':24})
        self.assertEqual(report['case_count'],32)
        self.assertEqual(report['new_human_reviews_collected'],0)
        self.assertEqual(report['papers_evaluated'],0)
        digest=report.pop('report_sha256')
        self.assertEqual(digest,ref.fingerprint(report))

    def test_gold_changes_cannot_change_engine_predictions(self):
        original=ref.compare()
        packet=json.loads(ref.CASES.read_text())
        packet['cases'][0]['expected_status']='REFUTED'
        raw=json.dumps(packet).encode()
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'cases.json';source.write_bytes(raw)
            with patch.object(ref,'CASES',source),patch.object(ref,'CASES_SHA',hashlib.sha256(raw).hexdigest()):
                changed=ref.compare()
        self.assertEqual([r['result'] for r in original['cases']],[r['result'] for r in changed['cases']])
        self.assertEqual(changed['comparison_status'],'MISMATCHED')
        self.assertEqual(changed['expectations_met'],31)

    def test_changed_sources_and_result_contract_stop(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'changed';source.write_bytes(b'changed')
            with self.assertRaises(ValueError):ref.pinned(source,ref.CASES_SHA)
        with patch.object(ref,'verify_toolkit_spec',return_value={'checks':[]}):
            with self.assertRaises(ValueError):ref.compare()

    def test_outputs_never_overwrite_frozen_reports(self):
        report=ref.compare()
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'report'
            ref.write_reports(out,report)
            before=out.with_suffix('.json').read_bytes()
            with self.assertRaises(FileExistsError):ref.write_reports(out,report)
            self.assertEqual(before,out.with_suffix('.json').read_bytes())
            text=out.with_suffix('.md').read_text()
            self.assertIn('32 / 32',text)
            self.assertIn('unknown_t',text)
