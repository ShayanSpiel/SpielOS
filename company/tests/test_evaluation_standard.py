"""Actual contract regressions; synthetic fixtures never qualify a Director model."""
from copy import deepcopy
import tempfile
from pathlib import Path
import unittest

from company.evals.standard import STANDARD, starter_suite, validate_suite, validate_standard, matched
from company.evals.contracts import check_rule
from company.evals.harness import EvaluationHarness
from company.tests.test_bounded_workflow_runs import manifest
from company.workflows.runs import WorkflowRuntime


def contract_case(inputs):
    """Exercise the actual validator, with one labeled faulty-output control."""
    candidate=manifest()['evaluation']
    if inputs['case']=='filename-only':
        candidate['cases'][0]['input']={'path':'/fixtures/order.json'}
    elif inputs['case']=='missing-question':
        candidate['criteria'][0].pop('question')
    try:
        validate_standard(candidate)
        allowed=True
    except ValueError:
        allowed=False
    if inputs.get('fault_injection'):
        allowed=not allowed
    return {'accepted':allowed,'explanation':'Actual validator accepted the contract' if allowed else 'Actual validator rejected the incomplete evaluation contract'}


def contract_case_regression(inputs):
    result=contract_case(inputs)
    if inputs['case']=='complete':result['accepted']=False
    return result


def conformance_suite():
    criteria=[{'id':'correct-verdict','source':'Evaluation standard v2','question':'Does validation accept complete evaluations and reject provenance-only specifications?',
        'dimension':'behavior','anchors':{'pass':'Observed acceptance matches the specified contract policy','fail':'Observed acceptance contradicts the contract policy'},
        'severity':'block','evaluator':'check','check':{'kind':'equals_input','path':'/accepted','input_path':'/expected_allowed'}}]
    cases=[]
    for name,split,case,expected_allowed,fault,expected in [
        ('complete','representative','complete',True,False,'pass'),
        ('provenance-only','held_out','filename-only',False,False,'pass'),
        ('missing-question','representative','missing-question',False,False,'pass'),
        ('faulty-validator-control','negative','filename-only',False,True,'fail')]:
        cases.append({'id':name,'split':split,'intent':'Reject file references as a substitute for a quality test' if case!='complete' else 'Accept an executable evaluation with meaningful inputs and expected results',
            'input':{'case':case,'expected_allowed':expected_allowed,'fault_injection':fault},
            'reference':{'accepted':expected_allowed,'explanation':'Expected policy decision on the provided evaluation contract'},
            'expected':expected,**({'failure_criteria':['correct-verdict']} if expected=='fail' else {})})
    return {'id':'evaluation-contract-conformance','version':'2',
        'input_schema':{'type':'object','required':['case','expected_allowed','fault_injection'],'properties':{'case':{'type':'string'},'expected_allowed':{'type':'boolean'},'fault_injection':{'type':'boolean'}}},
        'output_schema':{'type':'object','required':['accepted','explanation'],'properties':{'accepted':{'type':'boolean'},'explanation':{'type':'string'}}},
        'evaluation':{'standard':STANDARD,'subject':'system_improvement','objective':'Prove the validator distinguishes a meaningful evaluation from filename-only evidence, and catches a deliberately faulty verdict',
                      'version':'2','criteria':criteria,'cases':cases}}


class EvaluationStandardTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.runtime=WorkflowRuntime(Path(self.directory.name)/'workflow.sqlite')

    def test_all_five_subjects_have_explicit_review_obligations_and_unqualified_templates(self):
        for subject in ('director','build','system_improvement','workflow','agent'):
            suite=starter_suite(subject)
            validate_suite(suite)
            self.assertGreaterEqual(len(suite['evaluation']['coverage_obligations']),6)
            self.assertIn('unqualified',suite['readiness'])

    def test_path_only_cases_and_vague_rubrics_cannot_be_new_candidates(self):
        spec=manifest('host');spec['evaluation']['cases'][0]['input']={'path':'/fake/input.json'}
        with self.assertRaisesRegex(ValueError,'inspectable'):self.runtime.candidate(spec)
        spec=manifest('host');spec['evaluation']['criteria'][0]['anchors']='good enough'
        with self.assertRaisesRegex(ValueError,'anchors'):self.runtime.candidate(spec)
        spec=manifest('host');spec['evaluation'].pop('standard')
        with self.assertRaisesRegex(ValueError,'legacy'):self.runtime.candidate(spec)

    def test_wrong_failure_cannot_qualify_a_negative_case(self):
        case={'expected':'fail','failure_criteria':['permission']}
        report={'state':'fail','coverage_complete':True,'criteria':{'permission':{'state':'pass'},'readability':{'state':'fail'}}}
        self.assertFalse(matched(case,report))

    def test_subjective_rating_needs_actual_artifact_evidence(self):
        from company.workflows.runs import digest
        suite=starter_suite('director');case=suite['evaluation']['cases'][0]
        output={'answer':'The correction applies to this order only.','events':[]}
        incomplete={'task-quality':{'state':'pass','reason':'Looks fine'}}
        result=self.runtime.evaluate(suite,output,inputs=case['input'],case_id=case['id'],verdicts=incomplete,evaluator='independent-reviewer')
        self.assertEqual(result['state'],'missing')
        incomplete['task-quality'].update(artifact_digest=digest(output),evidence=['The answer explicitly limits the correction to this order.'])
        result=self.runtime.evaluate(suite,output,inputs=case['input'],case_id=case['id'],verdicts=incomplete,evaluator='independent-reviewer')
        self.assertEqual(result['state'],'pass')

    def test_behavior_checks_inspect_event_content_and_order(self):
        output={'events':[{'kind':'feedback','scope':'run'},{'kind':'boundary'},{'kind':'deliver'}]}
        rule={'kind':'event_order','path':'/events','sequence':[{'/kind':'feedback','/scope':'run'},{'/kind':'boundary'},{'/kind':'deliver'}]}
        self.assertTrue(check_rule(rule,output,{}))
        self.assertFalse(check_rule(rule,{'events':list(reversed(output['events']))},{}))
        self.assertTrue(check_rule({'kind':'event_count','path':'/events','match':{'/kind':'publish'},'max':0},output,{}))
        self.assertFalse(check_rule({'kind':'event_count','path':'/events','match':{'/kind':'publish'},'max':0},{'events':[{'kind':'publish'}]},{}))

    def test_actual_experiments_are_paired_and_local_pass_needs_remote_verification(self):
        harness=EvaluationHarness(self.runtime);suite=harness.register(conformance_suite())
        baseline=harness.experiment(suite,task=contract_case,name='Actual validator conformance',request_key='baseline')
        self.assertTrue(baseline['local_pass']);self.assertEqual(baseline['state'],'awaiting_telemetry')
        self.assertFalse(baseline['model_behavior_qualified'])
        candidate=harness.experiment(suite,task=contract_case_regression,name='Labeled regression control',request_key='regression')
        comparison=harness.compare(baseline['id'],candidate['id'])
        self.assertEqual(comparison['regressions'],['complete']);self.assertFalse(comparison['eligible_for_review'])
        replay=harness.experiment(suite,task=contract_case,name='Actual validator conformance',request_key='baseline')
        self.assertEqual([i['event_id'] for i in replay['items']],[i['event_id'] for i in baseline['items']])
        with self.assertRaisesRegex(ValueError,'another suite'):
            harness.experiment(suite,task=contract_case_regression,name='Changed task',request_key='baseline')

    def test_changed_judge_or_dataset_is_not_a_comparable_experiment(self):
        harness=EvaluationHarness(self.runtime);suite=conformance_suite();left=harness.register(suite)
        first=harness.experiment(left,task=contract_case,name='Baseline',request_key='left')
        suite=deepcopy(suite);suite['evaluation']['version']='3';right=harness.register(suite)
        second=harness.experiment(right,task=contract_case,name='Changed evaluator',request_key='right')
        with self.assertRaisesRegex(ValueError,'same immutable'):harness.compare(first['id'],second['id'])
