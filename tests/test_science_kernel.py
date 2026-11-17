"""Independent proof kernel: exact arithmetic, evidence, countermodels and rechecks."""
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.science_kernel import prove_science
from sra.science_certificate import verify_science_certificate
from sra.science_kernel_spec import canonical, digest, prepare_science_problem

ROOT = Path(__file__).parents[1]


def atom(name):
    return {'atom': name}


def op(name, *args):
    return dict(op=name, args=list(args))


def minimal():
    return dict(schema_version='1.0', atoms=['a','b'], facts=[], arithmetic=[], rules=[],
                claims=[dict(id='goal', scope='declared_problem', expression=atom('a'))])


def checked(spec):
    report = prove_science(spec)
    assert verify_science_certificate(spec, report)['valid']
    return report


class ScienceKernelTests(unittest.TestCase):
    def test_four_scoped_example_and_reproducibility(self):
        value=json.loads((ROOT/'examples/scientific-proof.json').read_text())
        before=copy.deepcopy(value)
        report=checked(value)
        self.assertEqual(report,prove_science(value))
        import jsonschema
        schema=json.loads((ROOT/'schemas/scientific-proof.schema.json').read_text())
        jsonschema.validate(report,schema)
        self.assertEqual(value,before)
        self.assertEqual([row['status'] for row in report['claims']],['ENTAILED','UNRESOLVED','ENTAILED','ENTAILED','CONTRADICTED'])
        self.assertTrue(all(v=='NOT_ASSESSED' for v in report['scientific_assessment'].values()))
        self.assertEqual(report['arithmetic'][0]['left_bounds'],['3/10','3/10'])
        self.assertFalse(verify_science_certificate(value,'not JSON')['valid'])
        self.assertFalse(verify_science_certificate(value,[])['valid'])

    def test_unknown_atoms_have_both_worlds_and_no_closed_world_assumption(self):
        value=minimal()
        value['facts']=[dict(id='unknown',atom='a',origin='assumption',value=None)]
        report=checked(value)
        claim=report['claims'][0]
        self.assertEqual(claim['status'],'UNRESOLVED')
        self.assertEqual((claim['supporting_models'],claim['counter_models']),(2,2))
        self.assertTrue(claim['supporting_world']['assignment']['a'])
        self.assertFalse(claim['counter_world']['assignment']['a'])
        self.assertEqual(claim['basis_ids'],[])

    def test_consistent_conclusions_basis_and_no_explosion_on_conflict(self):
        value=minimal()
        value['facts']=[dict(id='A',atom='a',value=True,origin='assumption'),dict(id='B',atom='b',value=True,origin='assumption')]
        report=checked(value)
        self.assertEqual(report['claims'][0]['basis_ids'],['A'])
        value['facts'].append(dict(id='C',atom='a',value=False,origin='assumption'))
        value['claims'].append(dict(id='tautology',scope='declared_problem',expression={'const':True}))
        report=checked(value)
        self.assertEqual(report['basis_state'],'INCONSISTENT')
        self.assertEqual(report['conflict_core'],['A','C'])
        self.assertTrue(all(row['status']=='UNRESOLVED' for row in report['claims']))
        self.assertTrue(all(row['supporting_world'] is None for row in report['claims']))

    def test_logical_operators_and_empty_tautology_basis(self):
        value=minimal()
        expressions=[op('iff',atom('a'),atom('a')),op('or',atom('a'),op('not',atom('a'))),
                     op('implies',{'const':False},atom('a')),op('and',atom('a'),{'const':False}),
                     op('not',op('iff',atom('a'),atom('a')))]
        value['claims']=[dict(id=f'C{i}',scope='declared_problem',expression=expr) for i,expr in enumerate(expressions)]
        report=checked(value)
        self.assertEqual([row['status'] for row in report['claims']],['ENTAILED']*3+['CONTRADICTED']*2)
        self.assertTrue(all(row['basis_ids']==[] for row in report['claims']))

    def test_exact_intervals_all_relations_and_large_cancellation(self):
        cases=[(op('add','0.1','0.2'),'0.3','eq',True),
               (op('sub','1000000000000.0000001','1000000000000'),'0.0000001','eq',True),
               (op('mul',{'interval':['-1','1']},{'interval':['-2','3']}),'4','lt',True),
               (op('sub',{'interval':[1,2]},{'interval':[3,5]}),'-1','le',True),
               (op('div',{'interval':[1,2]},{'interval':[-2,-1]}),'-1/2','le',True),
               (2,1,'gt',True),(1,1,'ge',True),(1,2,'ne',True),(1,1,'ne',False),
               (1,1,'lt',False),(2,1,'le',False),(1,2,'gt',False),(1,2,'ge',False),
               ({'interval':[0,2]},{'interval':[1,3]},'eq',None),
               ({'interval':[0,2]},{'interval':[1,3]},'ne',None),
               ({'interval':[0,2]},1,'le',None),(1,2,'eq',False)]
        for left,right,relation,expected in cases:
            with self.subTest(relation=relation):
                value=minimal();value['arithmetic']=[dict(id='N',atom='a',left=left,right=right,relation=relation)]
                report=checked(value)
                self.assertIs(report['arithmetic'][0]['value'],expected)
                self.assertEqual(report['claims'][0]['status'],{True:'ENTAILED',False:'CONTRADICTED',None:'UNRESOLVED'}[expected])

    def test_native_arithmetic_abstains_on_zero_divisors_and_resource_limits(self):
        huge=(1<<255)-1
        tree=huge
        for _ in range(5):
            tree=op('mul',tree,tree)
        failing=[op('div',1,{'interval':[-1,1]}),op('add',op('div',1,0),2),op('add',2,op('div',1,0)),tree,op('add',tree,1)]
        for term in failing:
            value=minimal();value['arithmetic']=[dict(id='N',atom='a',left=term,right=0,relation='eq')]
            report=checked(value)
            self.assertIsNone(report['arithmetic'][0]['value'])
            self.assertIn(report['arithmetic'][0]['reason'],('DIVISOR_INCLUDES_ZERO','ARITHMETIC_RESOURCE_LIMIT'))
            self.assertEqual(report['claims'][0]['status'],'UNRESOLVED')
        value['arithmetic'][0].update(left=1,right=op('div',1,0))
        self.assertIsNone(checked(value)['arithmetic'][0]['right_bounds'])

    def test_source_identity_explicit_unicode_offsets_and_evidence_origins(self):
        value=minimal();snapshot='🙂The value is fixed.'
        value['sources']=[dict(id='S',text=snapshot,sha256=hashlib.sha256(snapshot.encode()).hexdigest())]
        ref=dict(source_id='S',quote='The value is fixed.',start=1)
        value['facts']=[dict(id='E',atom='a',value=True,origin='evidence',source_refs=[ref])]
        report=checked(value)
        self.assertEqual(report['premises'][0]['source_refs'][0]['end'],len(snapshot))
        value['arithmetic']=[dict(id='N',atom='b',left='1/3',right='1/3',relation='eq',source_refs=[ref])]
        self.assertTrue(verify_science_certificate(value,prove_science(value))['valid'])
        for change in ('hash','offset','unknown','quote','origin','duplicate'):
            bad=copy.deepcopy(value)
            if change=='hash':bad['sources'][0]['sha256']='0'*64
            if change=='offset':bad['facts'][0]['source_refs'][0]['start']=4
            if change=='unknown':bad['facts'][0]['source_refs'][0]['source_id']='absent'
            if change=='quote':bad['facts'][0]['source_refs'][0]['quote']='absent'
            if change=='origin':bad['facts'][0]['source_refs']=[]
            if change=='duplicate':bad['sources']*=2
            with self.subTest(change=change),self.assertRaises(ValueError):prepare_science_problem(bad)

    def test_rehashed_forged_certificates_are_rejected(self):
        value=minimal();value['facts']=[dict(id='A',atom='a',value=True,origin='assumption'),dict(id='B',atom='b',value=True,origin='assumption')]
        report=checked(value)
        modifications=[lambda c:c.update(kernel_sha256='0'*64),lambda c:c.update(admissible_worlds=99),
                       lambda c:c.update(conflict_core=['A']),lambda c:c.update(claims=[]),
                       lambda c:c['claims'][0].update(status='CONTRADICTED'),
                       lambda c:c['claims'][0].update(basis_ids=[]),lambda c:c['claims'][0].update(basis_ids=['A','B']),
                       lambda c:c['claims'][0].update(basis_ids=['A','A']),lambda c:c['claims'][0].update(basis_ids=[{}]),
                       lambda c:c['claims'][0].update(basis_ids=['missing']),lambda c:c.update(claims=[3]),
                       lambda c:c['claims'][0]['supporting_world']['assignment'].update(a=1)]
        for change in modifications:
            bad=copy.deepcopy(report);change(bad);bad['certificate_sha256']=digest({k:v for k,v in bad.items() if k!='certificate_sha256'})
            with self.subTest(change=change):self.assertFalse(verify_science_certificate(value,bad)['valid'])
        bad=copy.deepcopy(report);bad['certificate_sha256']='0'*64
        self.assertFalse(verify_science_certificate(value,bad)['valid'])
        unknown=minimal();bad=checked(unknown);bad['claims'][0]['basis_ids']=['A'];bad['certificate_sha256']=digest({k:v for k,v in bad.items() if k!='certificate_sha256'})
        self.assertFalse(verify_science_certificate(unknown,bad)['valid'])
        value['facts'].append(dict(id='opposite',atom='a',value=False,origin='assumption'))
        bad=checked(value);bad['conflict_core']=['A'];bad['certificate_sha256']=digest({k:v for k,v in bad.items() if k!='certificate_sha256'})
        self.assertFalse(verify_science_certificate(value,bad)['valid'])

    def test_checker_accepts_alternative_valid_minimal_basis_without_calling_prover(self):
        value=minimal();value['facts']=[dict(id=name,atom='a',value=True,origin='assumption') for name in ('A','B')]
        report=checked(value)
        report['claims'][0]['basis_ids']=['A'] if report['claims'][0]['basis_ids']==['B'] else ['B']
        report['certificate_sha256']=digest({k:v for k,v in report.items() if k!='certificate_sha256'})
        with patch('sra.science_kernel.prove_science',side_effect=AssertionError('must not call prover')):
            self.assertTrue(verify_science_certificate(value,report)['valid'])

    def test_bounds_validation_inert_language_and_no_partial_certificate(self):
        invalid=[]
        for field,new in [('atoms',[]),('atoms',['a','a']),('atoms',['bad name']),('atoms',[f'a{i}' for i in range(17)]),('schema_version','other'),('claims',[])]:
            value=minimal();value[field]=new;invalid.append(value)
        for expr in (True,{'atom':'unknown'},{'const':1},op('__import__','os'),op('and',atom('a')),op('not',atom('a'),atom('b')),op('implies',atom('a')),{'atom':'a','extra':1}):
            value=minimal();value['claims'][0]['expression']=expr;invalid.append(value)
        for left in (1.0,True,'NaN','1/0','1e99',1<<256,{'interval':[2,1]},{'interval':[1]},op('add',1),{'op':'bad','args':[1,2]}):
            value=minimal();value['arithmetic']=[dict(id='N',atom='a',left=left,right=1,relation='eq')];invalid.append(value)
        for fields in (dict(atom='unknown'),dict(value=1),dict(origin='automatic'),dict(id='goal')):
            value=minimal();value['facts']=[dict(dict(id='A',atom='a',value=True,origin='assumption'),**fields)];invalid.append(value)
        value=minimal();value['claims'][0]['scope']='global_scientific_truth';invalid.append(value)
        value=minimal();value['arithmetic']=[dict(id='N',atom='missing',left=1,right=1,relation='eq')];invalid.append(value)
        term=atom('a')
        for _ in range(18):term=op('not',term)
        value=minimal();value['claims'][0]['expression']=term;invalid.append(value)
        value=minimal();value['claims']=[dict(id=f'C{i}',scope='declared_problem',expression=op('and',*([{'const':True}]*16))) for i in range(32)];invalid.append(value)
        value=minimal();value['sources']=[dict(id=f'S{i}',text='x'*100000,sha256=hashlib.sha256(b'x'*100000).hexdigest()) for i in range(3)];invalid.append(value)
        value=minimal();value['sources']=[dict(id='S',text=' ',sha256=hashlib.sha256(b' ').hexdigest())];invalid.append(value)
        for value in invalid:
            with self.subTest(value=str(value)[:80]),self.assertRaises(ValueError):prepare_science_problem(value)
        for value in ('{"schema_version":"1.0","schema_version":"1.0"}', 'NaN', {'bad':object()}, 'x'*(1024*1024+1)):
            with self.assertRaises(ValueError):prepare_science_problem(value)
        with patch('sra.science_kernel.MAX_BYTES',10),self.assertRaises(ValueError):prove_science(minimal())

    def test_maximum_atom_universe_and_independent_recheck(self):
        value=minimal();value['atoms']=[f'a{i}' for i in range(16)];value['claims'][0]['expression']=atom('a15')
        report=checked(value)
        self.assertEqual(report['universe_worlds'],65536)
        self.assertEqual(report['claims'][0]['supporting_models'],32768)

    @unittest.skipUnless(importlib.util.find_spec('z3'), 'Optional Z3 cross-check not installed')
    def test_seeded_boolean_problems_match_external_z3(self):
        import z3
        rng=random.Random(771)
        def formula(depth):
            if depth==0:return atom(rng.choice(['a','b']))
            choice=rng.choice(['and','or','not','implies','iff'])
            return op(choice,formula(depth-1),formula(depth-1)) if choice!='not' else op(choice,formula(depth-1))
        variables={name:z3.Bool(name) for name in ('a','b')}
        def translate(expr):
            if 'atom' in expr:return variables[expr['atom']]
            args=[translate(arg) for arg in expr['args']]
            return {'and':lambda:z3.And(*args),'or':lambda:z3.Or(*args),'not':lambda:z3.Not(args[0]),'implies':lambda:z3.Implies(*args),'iff':lambda:args[0]==args[1]}[expr['op']]()
        for _ in range(24):
            value=minimal();value['rules']=[dict(id='R',expression=formula(2))];value['claims'][0]['expression']=formula(2)
            premise=translate(value['rules'][0]['expression']);claim=translate(value['claims'][0]['expression'])
            def sat(*args):
                solver=z3.Solver();solver.add(*args);return solver.check()==z3.sat
            expected='UNRESOLVED' if not sat(premise) else 'ENTAILED' if not sat(premise,z3.Not(claim)) else 'CONTRADICTED' if not sat(premise,claim) else 'UNRESOLVED'
            self.assertEqual(checked(value)['claims'][0]['status'],expected)
