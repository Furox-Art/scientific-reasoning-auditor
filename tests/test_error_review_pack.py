"""Packet/collection software controls; no real human labels are fabricated."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.error_review_pack import build_pack, main, merge_reviews, review_sheet
from sra.error_benchmark import prepare_manifest
from test_error_benchmark import fixture


def completed(cohort, slot):
    sheet = review_sheet(cohort, slot)
    sheet['reviewer_id'] = 'synthetic_' + slot
    for row in sheet['cases']:
        row.update(label='uncertain', rationale='Synthetic collection software control, not a human judgment.')
    return sheet


class ErrorReviewPackTests(unittest.TestCase):
    def setUp(self):
        self.manifest = fixture()
        self.cohort = prepare_manifest(self.manifest)

    def test_pilot_recipe_and_instructions_are_bound_by_source_inventory(self):
        from sra.provenance import _source_tree_sha256
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pilot = root/'benchmarks/pilots'
            pilot.mkdir(parents=True)
            (pilot/'recipe.json').write_text('{}', encoding='utf-8')
            (pilot/'README.md').write_text('Instructions', encoding='utf-8')
            first, scope, files = _source_tree_sha256(root)
            self.assertEqual(files, ['benchmarks/pilots/README.md', 'benchmarks/pilots/recipe.json'])
            self.assertIn('Offline pilot recipes', scope)
            (pilot/'recipe.json').write_text('{"changed":true}', encoding='utf-8')
            self.assertNotEqual(first, _source_tree_sha256(root)[0])
            second = _source_tree_sha256(root)[0]
            (pilot/'README.md').write_text('Changed instructions', encoding='utf-8')
            self.assertNotEqual(second, _source_tree_sha256(root)[0])

    def test_independent_blank_sheets_and_no_predictions(self):
        a, b = [review_sheet(self.cohort, s) for s in ('A', 'B')]
        self.assertNotEqual(a['reviewer_slot'], b['reviewer_slot'])
        self.assertIsNone(a['reviewer_id'])
        self.assertEqual(len(a['cases']), len(self.manifest['cases']))
        self.assertTrue(all(c['label'] is None and c['rationale'] == '' for c in a['cases']))
        self.assertNotIn('prediction', json.dumps(a))
        with self.assertRaises(ValueError):
            review_sheet(self.cohort, 'C')
        with self.assertRaises(ValueError):
            merge_reviews(self.manifest, a, b)

    def test_merge_preserves_unknowns_and_inputs(self):
        a, b = [completed(self.cohort, s) for s in ('A', 'B')]
        a['cases'][0]['label'] = b['cases'][0]['label'] = 'not_applicable'
        before = copy.deepcopy((self.manifest, a, b))
        result = merge_reviews(self.manifest, json.dumps(a), b)
        self.assertEqual(result['cases'][0]['reviewers'][0]['label'], 'not_applicable')
        self.assertEqual(result['cases'][1]['reviewers'][1]['label'], 'uncertain')
        self.assertEqual(result['label_origin'], 'synthetic_fixture')
        self.assertEqual(before, (self.manifest, a, b))

    def test_rejects_incomplete_wrong_duplicate_or_tampered_sheets(self):
        a, b = [completed(self.cohort, s) for s in ('A', 'B')]
        mutations = []
        for key, val in [('schema_version', 'wrong'), ('manifest_sha256', '0'*64),
                         ('reviewer_slot', 'B'), ('reviewer_id', b['reviewer_id']),
                         ('reviewer_id', None), ('unexpected', True)]:
            bad = copy.deepcopy(a); bad[key] = val; mutations.append(bad)
        for cases in [a['cases'][:-1], a['cases'] + [a['cases'][0]], [], None]:
            bad = copy.deepcopy(a); bad['cases'] = cases; mutations.append(bad)
        for key, val in [('label', None), ('label', 'negative'), ('rationale', 'short'),
                         ('rationale', ' '*30), ('rationale', 'x'*2001), ('unexpected', True)]:
            bad = copy.deepcopy(a); bad['cases'][0][key] = val; mutations.append(bad)
        for bad in mutations:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                merge_reviews(self.manifest, bad, b)

    def test_disagreement_requires_distinct_actual_adjudication(self):
        a, b = [completed(self.cohort, s) for s in ('A', 'B')]
        b['cases'][0]['label'] = 'not_applicable'
        with self.assertRaises(ValueError):
            merge_reviews(self.manifest, a, b)
        third = dict(schema_version='error-adjudications/1.0', manifest_sha256=self.cohort['manifest_sha256'], cases=[
            dict(id=a['cases'][0]['id'], reviewer_id='synthetic_third', label='uncertain',
                 rationale='Synthetic adjudication control, not a real independent review.')])
        result = merge_reviews(self.manifest, a, b, third)
        self.assertEqual(result['cases'][0]['adjudication']['reviewer_id'], 'synthetic_third')
        for change in [('reviewer_id', a['reviewer_id']), ('id', 'unknown'), ('label', None), ('rationale', '')]:
            bad = copy.deepcopy(third); bad['cases'][0][change[0]] = change[1]
            with self.assertRaises(ValueError):merge_reviews(self.manifest, a, b, bad)
        for key, val in [('schema_version', 'wrong'), ('manifest_sha256', '0'*64), ('cases', None)]:
            bad = copy.deepcopy(third); bad[key] = val
            with self.assertRaises(ValueError):merge_reviews(self.manifest, a, b, bad)

    def test_empty_adjudication_and_explicit_agreement_override(self):
        a, b = [completed(self.cohort, s) for s in ('A', 'B')]
        third = dict(schema_version='error-adjudications/1.0', manifest_sha256=self.cohort['manifest_sha256'], cases=[])
        self.assertIsNone(merge_reviews(self.manifest, a, b, third)['cases'][0]['adjudication'])
        third['cases'] = [dict(id=a['cases'][0]['id'], reviewer_id='synthetic_third', label='not_applicable',
                               rationale='Synthetic explicit override for collection software only.')]
        self.assertEqual(merge_reviews(self.manifest, a, b, third)['cases'][0]['adjudication']['label'], 'not_applicable')

    def test_packet_hashes_blinding_full_sources_and_determinism(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xml = b'<article><front>Front</front><body><p>F(1, 20) = 2.50, p = .13</p></body><back>References</back></article>'
            pdf = b'%PDF-1.4 synthetic software fixture only'
            paper = dict(pmcid='PMC0', discipline='synthetic', title='Synthetic paper', authors=['Test Fixture'], doi='synthetic:doi',
                         copyright='Synthetic', license='MIT', license_url='synthetic:license', publisher_url='synthetic:paper',
                         cases=[dict(id='test_case', paragraph_index=0, pdf_page=1, quote='F(1, 20) = 2.50, p = .13',
                                     test='F', statistic='2.50', df=[1,20], reported_p='.13', relation='=', mapping_note='Synthetic only')])
            paper['files'] = {}
            for ext, raw in [('xml', xml), ('pdf', pdf)]:
                (root/f'PMC0.{ext}').write_bytes(raw)
                paper['files'][ext] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            recipe = dict(pilot_id='synthetic_pack_control', included=[paper])
            with patch('sra.toolkit._backend', side_effect=AssertionError('No numerical backend permitted')):
                raw = build_pack(root, recipe)
                self.assertEqual(raw, build_pack(root, recipe))
            with zipfile.ZipFile(io.BytesIO(raw)) as outer:
                manifest = json.loads(outer.read('organizer/manifest.json'))
                self.assertIn('Front', manifest['papers'][0]['text'])
                self.assertIn('References', manifest['papers'][0]['text'])
                self.assertEqual(len(prepare_manifest(manifest)['cases']), 1)
                for slot in ('A', 'B'):
                    with zipfile.ZipFile(io.BytesIO(outer.read(f'reviewer-{slot}.zip'))) as inner:
                        self.assertEqual(inner.read('sources/PMC0.pdf'), pdf)
                        self.assertEqual(inner.read('sources/PMC0.xml'), xml)
                        sheet = json.loads(inner.read('review-sheet.json'))
                        self.assertIsNone(sheet['reviewer_id'])
                        self.assertIsNone(sheet['cases'][0]['label'])
                        index = json.loads(inner.read('source-index.json'))
                        self.assertNotIn('cases', index['included'][0])
                        self.assertNotIn('manifest.json', ' '.join(inner.namelist()))
                        for line in inner.read('SHA256SUMS').decode().splitlines():
                            sha, name = line.split('  ', 1)
                            self.assertEqual(sha, hashlib.sha256(inner.read(name)).hexdigest())
                for line in outer.read('SHA256SUMS').decode().splitlines():
                    sha, name = line.split('  ', 1)
                    self.assertEqual(sha, hashlib.sha256(outer.read(name)).hexdigest())
            (root/'PMC0.xml').write_bytes(xml+b' ')
            with self.assertRaises(ValueError):build_pack(root, recipe)
            (root/'PMC0.xml').write_bytes(xml.replace(b'Front', b'Wrong'))
            with self.assertRaises(ValueError):build_pack(root, recipe)
            (root/'PMC0.xml').write_bytes(xml)
            paper['cases'][0]['quote'] = 'not present'
            with self.assertRaises(ValueError):build_pack(root, recipe)

    def test_cli_exclusive_outputs_and_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
            for slot in ('A', 'B'):
                (root/f'{slot}.json').write_text(json.dumps(completed(self.cohort, slot)), encoding='utf-8')
            argv = ['merge', '--manifest', str(root/'manifest.json'), '--reviewer-a', str(root/'A.json'),
                    '--reviewer-b', str(root/'B.json'), '--out', str(root/'labels.json')]
            main(argv)
            self.assertEqual(len(json.loads((root/'labels.json').read_text())['cases']), len(self.manifest['cases']))
            with self.assertRaises(FileExistsError):main(argv)
            with patch('tools.error_review_pack.build_pack', return_value=b'ZIP'):
                main(['build','--sources',str(root),'--out',str(root/'packet.zip')])
            self.assertEqual((root/'packet.zip').read_bytes(), b'ZIP')


if __name__ == '__main__':
    unittest.main()
