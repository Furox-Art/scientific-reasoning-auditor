"""Synthetic reference-adapter controls; no fabricated real human assessments."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import evaluate_published_reference as ref


def workbook(rows, shared=False):
    from xml.sax.saxutils import escape
    headers=['authors','statRaw','plosError','plosErrorLogical','plosValue','plosComputed','plosComment']
    data=[headers]+[[str(row.get(key,'')) for key in headers] for row in rows]
    strings=[]
    xml=[]
    for n, values in enumerate(data,1):
        cells=[]
        for c,value in enumerate(values):
            address=f'{chr(65+c)}{n}'
            if shared:
                strings.append(value);cells.append(f'<c r="{address}" t="s"><v>{len(strings)-1}</v></c>')
            else:cells.append(f'<c r="{address}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
        xml.append(f'<row r="{n}">'+''.join(cells)+'</row>')
    stream=io.BytesIO()
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}"><sheets><sheet name="p1148checked"/></sheets></workbook>')
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><sheetData>'+''.join(xml)+'</sheetData></worksheet>')
        if shared:z.writestr('xl/sharedStrings.xml',f'<sst xmlns="{ns}">'+''.join('<si><t>'+escape(s)+'</t></si>' for s in strings)+'</sst>')
    return stream.getvalue()


def fixture():
    def row(group,raw,gold):
        return dict(authors=group,statRaw=raw,plosError='' if gold is None else str(1-gold),
                    plosErrorLogical='' if gold is None else str(gold))
    return [row('Synthetic_A','t(20) = 3.00, p = .007',0),
            row('Synthetic_A','t(20) = 3.00, p = .8',1),
            row('Synthetic_B','',1),row('Synthetic_B','F(1.5, 20) = 5.00, p < .05',0),
            row('Synthetic_C','t(20) = 3.00, p = .007',None),
            row('Synthetic_Stapel_exclusion','t(20) = 3.00, p = .8',1)]


class PublishedReferenceTests(unittest.TestCase):
    def test_workbook_preserves_literals_and_source_rows(self):
        for shared in (False,True):
            rows=ref.read_workbook(workbook(fixture(),shared))
            self.assertEqual(len(rows),6)
            self.assertEqual(rows[0]['statRaw'],'t(20) = 3.00, p = .007')
            self.assertEqual(rows[0]['source_row'],2)

    def test_raw_parser_keeps_precision_and_abstains_without_guessing(self):
        check,reason=ref.parse_expression('  t(20) = −3.00, p = .007.  ','case')
        self.assertIsNone(reason)
        self.assertEqual(check['statistic'],'-3.00')
        self.assertEqual(check['reported_p'],'.007')
        self.assertEqual(check['df'],[20])
        for raw in ('','NA','2(1) = 5.00, p < .05','t(20) < 3.00, p < .05',
                    't(20) = 3.00, p <= .05','F(1.5,20) = 4.00, p < .05',
                    'r(20) = .5, p < .05','t(20) = 3.00, p = 2', 'x'*2001):
            with self.subTest(raw=raw):
                parsed,why=ref.parse_expression(raw,'case')
                self.assertIsNone(parsed);self.assertIsInstance(why,str)
        for raw,kind,df in [('F(1,20) = 4.00, p < .05','F',[1,20]),
                            ('Chi2(2) = 6.00, p < .05','chi2',[2])]:
            check,reason=ref.parse_expression(raw,'case')
            self.assertEqual(check['test'],kind);self.assertEqual(check['df'],df)

    def test_real_backend_counts_abstentions_and_exclusions(self):
        rows=ref.read_workbook(workbook(fixture()))
        before=copy.deepcopy(rows)
        result=ref.compare_rows(rows)
        self.assertEqual(result['summary']['confusion'],dict(tp=1,fp=0,tn=1,fn=0))
        self.assertEqual(result['summary']['abstentions'],dict(error=1,no_error=1))
        self.assertEqual(result['summary']['metrics']['reference_frame_recall']['value'],.5)
        self.assertNotIn('end_to_end_recall',result['summary']['metrics'])
        self.assertEqual(result['exclusions'],dict(no_manual_reference=1,source_study_exclusion=1))
        self.assertEqual(len(result['cases']),6)
        self.assertEqual(result['group_count'],2)
        self.assertEqual(len(result['group_omissions']),2)
        self.assertEqual(rows,before)

    def test_manual_adjustments_and_labels_cannot_change_predictions(self):
        rows=ref.read_workbook(workbook(fixture()))
        first=ref.compare_rows(rows)
        for row in rows:
            row.update(plosValue='999999',plosComputed='0',plosComment='one-tailed corrected reference note')
            if row['plosErrorLogical'] in ('0','1'):
                row['plosErrorLogical']=str(1-int(row['plosErrorLogical']))
                row['plosError']=str(1-int(row['plosError']))
        second=ref.compare_rows(rows)
        self.assertEqual([c['prediction'] for c in first['cases']],[c['prediction'] for c in second['cases']])
        self.assertEqual([c['check_result'] for c in first['cases']],[c['check_result'] for c in second['cases']])

    def test_invalid_reference_labels_stop_instead_of_becoming_negatives(self):
        for change in ({'plosErrorLogical':'TRUE'},{'plosError':'0'}, {'authors':''}):
            rows=ref.read_workbook(workbook(fixture()));rows[0].update(change)
            with self.assertRaises(ValueError):ref.compare_rows(rows)

    def test_backend_unavailability_is_partial_and_keeps_gold_denominators(self):
        rows=ref.read_workbook(workbook(fixture()))
        with patch('sra.toolkit._backend',side_effect=ImportError('synthetic missing backend')):
            result=ref.compare_rows(rows)
        self.assertEqual(result['execution_status'],'partial')
        self.assertEqual(result['summary']['binary_labeled_cases'],4)
        self.assertEqual(result['summary']['metrics']['decision_coverage']['value'],0)
        self.assertEqual(result['summary']['abstentions'],dict(error=2,no_error=2))

    def test_malformed_archives_and_unexpected_engine_results_are_rejected(self):
        for raw in (b'not a zip',b'x'*(2*1024*1024+1)):
            with self.assertRaises(ValueError):ref.read_workbook(raw)
        rows=ref.read_workbook(workbook(fixture()))
        with patch.object(ref,'verify_toolkit_spec',return_value={'checks':[]}):
            with self.assertRaises(ValueError):ref.compare_rows(rows)
        rows[0]['authors']='Synthetic_A'
        rows=rows[:1]
        self.assertEqual(ref.compare_rows(rows)['group_omissions'],[])

    def test_pin_guards_precede_execution_and_outputs_never_overwrite_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.xlsx';source.write_bytes(workbook(fixture()))
            with self.assertRaises(ValueError):ref.pinned_bytes(source,ref.WORKBOOK_SHA,2*1024*1024)
            expected=hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(ref.pinned_bytes(source,expected,2*1024*1024),source.read_bytes())
            out=root/'out';(root/'out.md').write_text('preserve')
            with self.assertRaises(FileExistsError):ref.write_reports(out,{'synthetic':'control'},'text')
            self.assertFalse((root/'out.json').exists())
            ref.write_reports(root/'new',{'synthetic':'control'},'text')
            self.assertEqual(json.loads((root/'new.json').read_text()),{'synthetic':'control'})

    def test_cached_logical_labels_are_read_but_predictor_formulas_are_rejected(self):
        import xml.etree.ElementTree as E
        def changed(raw, column, kind, value):
            z=zipfile.ZipFile(io.BytesIO(raw));files={n:z.read(n) for n in z.namelist()}
            tree=E.fromstring(files['xl/worksheets/sheet1.xml'])
            cell=next(c for c in tree.iter() if c.get('r')==column+'2')
            for child in list(cell):cell.remove(child)
            cell.set('t',kind)
            E.SubElement(cell,'{'+ref.NS['s']+'}f').text='IF(C2=1,FALSE,TRUE)'
            E.SubElement(cell,'{'+ref.NS['s']+'}v').text=value
            files['xl/worksheets/sheet1.xml']=E.tostring(tree)
            stream=io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as out:
                for name,payload in files.items():out.writestr(name,payload)
            return stream.getvalue()
        raw=workbook(fixture())
        cached=changed(raw,'D','b','0')
        cached=changed(cached,'E','e','#VALUE!')
        rows=ref.read_workbook(cached)
        self.assertEqual(rows[0]['plosErrorLogical'],'0')
        self.assertNotIn('plosValue',rows[0])
        for column in ('B','C'):
            with self.assertRaises(ValueError):ref.read_workbook(changed(raw,column,'b','1'))

    def test_engine_guard_rejects_changed_missing_extra_or_wrong_version_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);package=root/'sra';package.mkdir()
            (package/'__init__.py').write_bytes(b'__version__ = "0.9.0"\n')
            (package/'py.typed').write_bytes(b'')
            wheel=root/'synthetic-engine.whl'
            with zipfile.ZipFile(wheel,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('sra/__init__.py',(package/'__init__.py').read_bytes())
                z.writestr('sra/py.typed',b'')
            sha=hashlib.sha256(wheel.read_bytes()).hexdigest()
            with patch.object(ref,'WHEEL_SHA',sha),patch.object(ref.sra,'__file__',str(package/'__init__.py')):
                self.assertEqual(ref.verify_engine(wheel)['source_files_verified'],2)
                (package/'__init__.py').write_bytes(b'changed synthetic source\n')
                with self.assertRaises(ValueError):ref.verify_engine(wheel)
                (package/'__init__.py').write_bytes(b'__version__ = "0.9.0"\n')
                extra=package/'extra.py';extra.write_bytes(b'')
                with self.assertRaises(ValueError):ref.verify_engine(wheel)
                extra.unlink();(package/'py.typed').unlink()
                with self.assertRaises(ValueError):ref.verify_engine(wheel)
                with patch.object(ref.sra,'__version__','0.8.0'):
                    with self.assertRaises(ValueError):ref.verify_engine(wheel)
