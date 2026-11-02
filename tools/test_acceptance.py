#!/usr/bin/env python3
"""Execute realistic journeys and produce evidence; untested requirements stay pending."""
from pathlib import Path
import argparse,datetime,hashlib,json,sys,time,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def fingerprint():
    digest=hashlib.sha256()
    for folder in ('company','tools','bin'):
        for path in sorted((ROOT/folder).rglob('*')):
            if not path.is_file() or set(path.parts)&{'__pycache__','.pytest_cache'}:continue
            digest.update(path.relative_to(ROOT).as_posix().encode()+b'\0'+path.read_bytes()+b'\0')
    for filename in ('README.md','AGENTS.md','pyproject.toml','package.json','install.sh','.spielos-boundary.json'):
        path=ROOT/filename
        if path.is_file():digest.update(filename.encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()


class EvidenceResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.evidence={}
    def startTest(self,test):
        super().startTest(test)
        self.evidence[test.id()]={'scenarios':list(getattr(getattr(test,test._testMethodName),'scenarios',())),
                                  'status':'running'}
        self.started=time.monotonic()
    def stopTest(self,test):
        self.evidence[test.id()]['seconds']=round(time.monotonic()-self.started,6)
        if getattr(test,'measurements',None):self.evidence[test.id()]['measurements']=test.measurements
        super().stopTest(test)
    def addSuccess(self,test):
        super().addSuccess(test);self.evidence[test.id()]['status']='passed'
    def addFailure(self,test,error):
        super().addFailure(test,error);self.evidence[test.id()]['status']='failed'
    def addError(self,test,error):
        super().addError(test,error);self.evidence[test.id()]['status']='error'
    def addSkip(self,test,reason):
        super().addSkip(test,reason);self.evidence[test.id()].update(status='skipped',reason=reason)
    def addSubTest(self,test,subtest,error):
        super().addSubTest(test,subtest,error)
        if error:self.evidence[test.id()]['status']='failed'


def run(output):
    before=fingerprint()
    spec=json.loads((ROOT/'company/tests/scenarios/spec.json').read_text())
    suite=unittest.defaultTestLoader.discover(str(ROOT/'company/tests/scenarios'),top_level_dir=str(ROOT))
    result=unittest.TextTestRunner(verbosity=2,resultclass=EvidenceResult).run(suite)
    after=fingerprint()
    known={row['id'] for row in spec['scenarios']}
    unexpected=sorted({sid for row in result.evidence.values() for sid in row['scenarios']}-known)
    for scenario in spec['scenarios']:
        scenario['tests']=[name for name,row in result.evidence.items() if scenario['id'] in row['scenarios']]
        statuses=[result.evidence[name]['status'] for name in scenario['tests']]
        scenario['status']=('verified' if statuses and all(state=='passed' for state in statuses)
                            else 'failed' if any(state in {'failed','error'} for state in statuses) else 'pending')
    complete=all(row['status']=='verified' for row in spec['scenarios'])
    report={**spec,'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'source_sha256':before,'source_unchanged_during_tests':before==after,
            'tests':result.evidence,'unknown_scenario_ids':unexpected,
            'local_acceptance_complete':complete and result.wasSuccessful() and before==after and not unexpected,
            'overall_plan_complete':False}
    # External qualification needs real evidence; a local suite never certifies it.
    path=Path(output).expanduser().resolve()
    if path.is_relative_to(ROOT):raise ValueError('Store generated acceptance evidence outside product source')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+'\n')
    counts={state:sum(row['status']==state for row in spec['scenarios']) for state in ('verified','failed','pending')}
    print(json.dumps({'scenarios':counts,'report':str(path),'local_complete':report['local_acceptance_complete']}))
    return 1 if not result.wasSuccessful() or before!=after or unexpected else 0 if report['local_acceptance_complete'] else 2

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True)
    raise SystemExit(run(parser.parse_args().out))
