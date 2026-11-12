"""Restricted symbolic expressions with retained real-domain obligations."""
import ast
import itertools
import json
import subprocess
import sys
from fractions import Fraction

FUNCTIONS = ('sin','cos','exp','log','sqrt')


def prepare_symbolic(item):
    from sra.toolkit_spec import _fields, _NAME, _text, number
    required=('id','kind','variables','left','right')+(() if item['kind']=='symbolic_identity' else ('variable',))
    _fields(item,required)
    variables=item['variables']
    if not isinstance(variables,dict) or not 1 <= len(variables) <= 3 or any(
        not isinstance(k,str) or not _NAME.fullmatch(k) or k in FUNCTIONS or v not in ('real','positive','nonnegative','nonzero') for k,v in variables.items()):
        raise ValueError('Declare 1..3 variables with real, positive, nonnegative or nonzero assumptions.')
    if item['kind']!='symbolic_identity' and item['variable'] not in variables:
        raise ValueError('Calculus variable must be declared.')

    def parse(expression):
        expression=_text(expression,256).strip()
        try:
            tree=ast.parse(expression,mode='eval')
        except (SyntaxError,RecursionError) as exc:
            raise ValueError('Invalid symbolic expression.') from exc
        if sum(1 for _ in ast.walk(tree))>64:
            raise ValueError('Symbolic expression exceeds 64 syntax nodes.')
        calls=0
        def visit(node,depth=0,inside_function=False):
            nonlocal calls
            if depth>10:
                raise ValueError('Symbolic expression nesting exceeds 10 levels.')
            if isinstance(node,ast.Name) and node.id in variables:
                return ['symbol',node.id],1
            if isinstance(node,ast.Constant) and type(node.value) in (int,float):
                value=Fraction(number(ast.get_source_segment(expression,node)))
                return ['number',str(value)],1
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
                term,width=visit(node.operand,depth+1,inside_function)
                return ['neg' if isinstance(node.op,ast.USub) else 'pos',term],width
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in FUNCTIONS and len(node.args)==1 and not node.keywords and not inside_function:
                calls+=1
                if calls>4:
                    raise ValueError('At most four non-nested function calls per expression.')
                arg,_=visit(node.args[0],depth+1,True)
                return [node.func.id,arg],1
            if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Pow):
                if any(isinstance(part,ast.Pow) for part in ast.walk(node.left)):
                    raise ValueError('Nested powers are outside the symbolic resource contract.')
                power=node.right
                sign=-1 if isinstance(power,ast.UnaryOp) and isinstance(power.op,ast.USub) else 1
                power=power.operand if sign==-1 else power
                if not isinstance(power,ast.Constant) or type(power.value) is not int or not 0<=power.value<=4:
                    raise ValueError('Symbolic powers require integer literals in [-4,4].')
                base,width=visit(node.left,depth+1,inside_function)
                width=width**power.value
                result=['pow',base,sign*power.value]
            elif isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
                left,lw=visit(node.left,depth+1,inside_function)
                right,rw=visit(node.right,depth+1,inside_function)
                op={ast.Add:'add',ast.Sub:'sub',ast.Mult:'mul',ast.Div:'div'}[type(node.op)]
                width=lw+rw if op in ('add','sub') else lw*rw
                result=[op,left,right]
            else:
                raise ValueError('Unsupported symbolic syntax.')
            if width>256:
                raise ValueError('Symbolic expansion estimate exceeds 256 terms.')
            return result,width
        return visit(tree.body)[0]
    return {**item,'terms':[parse(item[key]) for key in ('left','right')]}


def compute_symbolic(item):
    import sympy as s
    symbols={k:s.Symbol(k,real=True,**({v:True} if v!='real' else {})) for k,v in item['variables'].items()}
    obligations=[]
    calculus=item['kind']!='symbolic_identity'
    def require(kind,value):
        established=getattr(value,'is_'+kind) is True
        obligations.append({'condition':f'{value} is {kind}','established':established})
    def build(term):
        op=term[0]
        if op=='symbol':
            return symbols[term[1]]
        if op=='number':
            return s.Rational(term[1])
        left=build(term[1])
        if op in ('neg','pos'):
            return -left if op=='neg' else left
        if op in FUNCTIONS:
            if op=='log':
                require('positive',left)
            if op=='sqrt':
                require('positive' if calculus else 'nonnegative',left)
            return getattr(s,op)(left,evaluate=False)
        if op=='pow':
            if term[2]<0:
                require('nonzero',left)
            return s.Pow(left,term[2],evaluate=False)
        right=build(term[2])
        if op=='div':
            require('nonzero',right)
            return s.Mul(left,s.Pow(right,-1,evaluate=False),evaluate=False)
        return {'add':lambda:s.Add(left,right,evaluate=False),
                'sub':lambda:s.Add(left,-right,evaluate=False),
                'mul':lambda:s.Mul(left,right,evaluate=False)}[op]()
    left,right=map(build,item['terms'])
    meaning='Conditional symbolic identity with explicit real-variable assumptions; not a proof of prose interpretation.'
    details={'meaning':meaning,'domain_obligations':obligations,'assumptions':item['variables']}
    if not all(o['established'] for o in obligations):
        return 'UNDETERMINED',details
    if item['kind']=='symbolic_derivative':
        left=s.diff(left,symbols[item['variable']])
    if item['kind']=='symbolic_antiderivative':
        right=s.diff(right,symbols[item['variable']])
    residual=s.cancel(s.trigsimp(s.expand_log(left-right,force=False)))
    details['residual']=str(residual)
    if residual==0:
        return 'VERIFIED',details
    ordered=list(symbols)
    for values in itertools.product((-2,-1,0,1,2),repeat=len(ordered)):
        if any((item['variables'][k]=='positive' and v<=0) or (item['variables'][k]=='nonnegative' and v<0) or (item['variables'][k]=='nonzero' and v==0) for k,v in zip(ordered,values)):
            continue
        value=residual.subs({symbols[k]:v for k,v in zip(ordered,values)})
        if value.is_finite is True and value.is_zero is False:
            details['counterexample']={k:v for k,v in zip(ordered,values)}
            return 'REFUTED',details
    return 'UNDETERMINED',details


def worker():
    result=compute_symbolic(json.loads(sys.stdin.read(16385)))
    sys.stdout.write(json.dumps(result,allow_nan=False))


def verify_symbolic(item,backend):
    try:
        result=subprocess.run([sys.executable,'-I','-c','from sra.symbolic import worker; worker()'],
            input=json.dumps(item),text=True,capture_output=True,timeout=5,check=False)
        if result.returncode or len(result.stdout)>65536:
            raise ValueError('Symbolic worker did not complete.')
        return tuple(json.loads(result.stdout))
    except subprocess.TimeoutExpired:
        return 'UNDETERMINED',{'meaning':'Symbolic worker reached its five-second budget; no proof is issued.'}
