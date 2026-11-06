"""Quality gates distinguish incorrect, missing, errored and subjective judgments."""
from copy import deepcopy
from company.evals.contracts import evaluate,calibration
from company.workflows.runs import digest
from .test_home import scenario
from .test_runtime import WorkspaceJourney,specification,report


class EvaluationJourneys(WorkspaceJourney):
    @scenario('evaluation.empty_duplicate_missing_coverage_blocked')
    def test_incomplete_harnesses_cannot_be_candidates_or_releases(self):
        for field,value in [('criteria',[]),('cases',[]),('cases',[specification()['evaluation']['cases'][0]]*2)]:
            spec=specification();spec['evaluation'][field]=value
            with self.subTest(field=field,value=value):
                with self.assertRaises(ValueError):self.runtime.candidate(spec)
        spec=specification();spec['evaluation']['criteria'].append({'id':'editorial','source':'Owner brief','question':'Is the output clear to its intended reader?','dimension':'output','anchors':{'pass':'The intended reader can identify the requested facts','fail':'The requested facts cannot be understood'},'severity':'block','evaluator':'human'})
        release=self.runtime.candidate(spec);case=spec['evaluation']['cases'][0]
        run=self.runtime.run(release,case['input'],request_key='missing-review',candidate_case=case['id'])
        checked=self.runtime.evaluate_run(run['id'])
        self.assertEqual(checked['evaluation']['criteria']['editorial']['state'],'missing')
        self.assertFalse(checked['evaluation']['coverage_complete'])
        self.assertEqual(checked['status'],'awaiting_evaluation')

    @scenario('evaluation.criterion_specific_checks_and_thresholds')
    def test_a_high_editorial_score_cannot_hide_an_incorrect_total(self):
        spec=specification();inputs={'title':'March','sales':[4,6]}
        spec['evaluation']['criteria'].append({'id':'clarity','source':'Owner brief examples','anchors':'1: immediately clear; 0: unusable',
            'severity':'warn','evaluator':'human','threshold':0.8,'threshold_reason':'Reviewed good examples score at least 0.8'})
        output={'title':'March','total':999,'rows':2}
        evaluation=evaluate(spec,output,inputs=inputs,verdicts={'clarity':{'state':'pass','score':1.0,'reason':'Readable typography','artifact_digest':digest(output),'evidence':['The reporting title is legible']}},evaluator='human-reviewer')
        self.assertEqual(evaluation['criteria']['total']['state'],'fail')
        self.assertEqual(evaluation['criteria']['rows']['state'],'pass')
        self.assertEqual(evaluation['state'],'fail')
        evaluation=evaluate(spec,report(inputs),inputs=inputs,verdicts={'clarity':{'state':'pass','score':0.7,'reason':'Below the anchored clarity example','artifact_digest':digest(report(inputs)),'evidence':['The title does not identify the reporting period clearly']}},evaluator='human-reviewer')
        self.assertEqual(evaluation['criteria']['clarity']['state'],'fail')
        # A warning remains visible without changing the block policy.
        self.assertEqual(evaluation['state'],'pass')

    @scenario('evaluation.error_and_not_applicable_policy')
    def test_inspection_errors_and_empty_applicability_are_not_quality_passes(self):
        spec=specification();inputs={'title':'March','sales':[4,6]}
        spec['evaluation']['criteria'][0]['check']['path']='/missing-field'
        result=evaluate(spec,report(inputs),inputs=inputs)
        self.assertEqual(result['criteria']['named']['state'],'error')
        self.assertEqual(result['state'],'error')
        spec=specification();case=spec['evaluation']['cases'][0]
        case['applicable_criteria']=[]
        result=evaluate(spec,case['reference'],inputs=case['input'],case_id=case['id'])
        self.assertEqual(result['state'],'missing')
        self.assertFalse(result['coverage_complete'])
        spec['evaluation']['criteria']=[{'id':'subjective','source':'brief','anchors':{'pass':'The title identifies the reporting period','fail':'The title is ambiguous'},
            'severity':'block','evaluator':'human'}]
        result=evaluate(spec,report(inputs),inputs=inputs,evaluator='reviewer',
            verdicts={'subjective':{'state':'not_applicable','reason':'Do not want to judge this'}})
        self.assertEqual(result['state'],'missing')

    @scenario('evaluation.model_judge_contract_and_calibration','evaluation.independent_review_and_self_judging_label')
    def test_model_judgment_requires_pinned_prompt_human_calibration_and_same_artifact(self):
        spec=specification();inputs={'title':'March','sales':[4,6]};output=report(inputs)
        calibration_rows=[{'case_id':'clear','human_state':'pass','judge_state':'pass','human_reviewer':'editor',
            'artifact_digest':digest({'title':'Clear reference'})},
            {'case_id':'unclear','human_state':'fail','judge_state':'fail','human_reviewer':'editor',
            'artifact_digest':digest({'title':'Unclear reference'})}]
        judge={'model':'synthetic-model-v1','prompt_digest':digest('Use the anchored editorial rubric'),'version':'judge-v1','calibration':calibration_rows}
        spec['evaluation']['criteria'].append({'id':'clarity','source':'Reviewed editorial examples','question':'Is the title clearly descriptive?','dimension':'output','anchors':{'pass':'The title identifies the reporting period','fail':'The title obscures the reporting period'},
            'severity':'block','evaluator':'model','threshold':0.8,'threshold_reason':'Bounded synthetic calibration examples', 'judge':judge})
        self.runtime.validate_manifest(spec)
        verdict={'state':'pass','score':0.9,'reason':'Uses an exact descriptive title','model':judge['model'],
            'prompt_digest':judge['prompt_digest'],'version':judge['version'],'artifact_digest':digest(output),
            'evidence':['The title identifies the reporting month.']}
        value=evaluate(spec,output,inputs=inputs,evaluator='same-agent',producer='same-agent',verdicts={'clarity':verdict})
        self.assertTrue(value['self_judged'])
        self.assertEqual(value['state'],'pass')
        changed=deepcopy(verdict);changed['prompt_digest']=digest('Unreviewed prompt')
        self.assertEqual(evaluate(spec,output,inputs=inputs,evaluator='judge',verdicts={'clarity':changed})['state'],'missing')
        spec['evaluation']['criteria'][-1]['judge']['calibration'][1]['judge_state']='pass'
        with self.assertRaisesRegex(ValueError,'disagrees'):self.runtime.validate_manifest(spec)
        with self.assertRaises(ValueError):calibration([])

    @scenario('evaluation.rendered_brand_artifact_inspected','portability.pinned_closure_and_brand_export')
    def test_brand_template_renders_at_mobile_and_desktop_and_release_pins_actual_assets(self):
        import base64,hashlib,json,os,re,shutil,subprocess,tempfile
        from pathlib import Path
        from company.branding import BrandRegistry,render_report
        from company.home import fingerprint
        from company.portability import PortablePackages
        browser=shutil.which('google-chrome') or shutil.which('chromium')
        mac=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        browser=browser or (str(mac) if mac.is_file() else None)
        if not browser:self.skipTest('A real Chromium renderer is required for rendered-media acceptance')
        brand=self.root/'company/brand'
        values={'company_name':'Synthetic example company','title':'Weekly sales report','description':'A bounded example based on three supplied receipts.',
                'metrics':[{'label':'Recorded sales','value':'159.00 USD'},{'label':'Receipts','value':'3'}],
                'source_note':'Synthetic fixture. Business impact has not been measured.'}
        page=brand/'examples/sales-report.html'
        page.write_text(render_report(brand,values).replace('</body>',"<script>document.body.dataset.overflow=String(document.documentElement.scrollWidth>innerWidth);document.body.dataset.cards=String(document.querySelectorAll('.metric-card').length)</script></body>"))
        import time,signal
        node=shutil.which('node')
        if not node:self.skipTest('Node with built-in WebSocket is required for exact browser viewport checks')
        renders=[]
        renderer=r'''const fs=require('node:fs');
(async()=>{
 const settings=JSON.parse(process.argv[1]);
 const targets=await (await fetch('http://127.0.0.1:'+settings.port+'/json/list')).json();
 const ws=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);
 const pending=new Map();let id=0;
 ws.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id&&pending.has(message.id)){
   const pair=pending.get(message.id);pending.delete(message.id);message.error?pair.reject(new Error(JSON.stringify(message.error))):pair.resolve(message.result);}});
 await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 function call(method,params={}){return new Promise((resolve,reject)=>{const next=++id;pending.set(next,{resolve,reject});ws.send(JSON.stringify({id:next,method,params}));});}
 await call('Page.enable');
 await call('Emulation.setDeviceMetricsOverride',{width:settings.width,height:settings.height,deviceScaleFactor:1,mobile:settings.width<600});
 await call('Page.navigate',{url:settings.url});
 let result;
 for(let attempt=0;attempt<50;attempt++){
   result=await call('Runtime.evaluate',{expression:'document.readyState',returnByValue:true});
   if(result.result.value==='complete')break;
   await new Promise(resolve=>setTimeout(resolve,50));
 }
 await call('Runtime.evaluate',{expression:'document.fonts.ready',awaitPromise:true});
 result=await call('Runtime.evaluate',{expression:'JSON.stringify({width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth,cards:document.querySelectorAll(".metric-card").length,text:document.body.innerText})',returnByValue:true});
 const shot=await call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,fromSurface:true});
 fs.writeFileSync(settings.output,Buffer.from(shot.data,'base64'));
 console.log(result.result.value);await call('Browser.close');ws.close();
})().catch(error=>{console.error(error.message);process.exitCode=1;});'''
        for width,height in [(390,844),(1280,900)]:
            image=brand/'examples'/('report-'+str(width)+'.png')
            with tempfile.TemporaryDirectory() as profile:
                process=subprocess.Popen([browser,'--headless','--disable-gpu','--no-first-run','--no-default-browser-check',
                    '--disable-background-networking','--disable-component-update','--hide-scrollbars',
                    '--user-data-dir='+profile,'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
                try:
                    port_file=Path(profile)/'DevToolsActivePort'
                    port=None
                    for attempt in range(300):
                        try:
                            lines=port_file.read_text().splitlines()
                            if len(lines)>=2 and lines[0].isdigit():
                                port=int(lines[0]);break
                        except FileNotFoundError:pass
                        if process.poll() is not None:break
                        time.sleep(0.05)
                    self.assertIsNotNone(port,'The isolated renderer did not publish a complete endpoint')
                    settings={'port':port,'width':width,'height':height,'url':page.as_uri(),'output':str(image)}
                    result=subprocess.run([node,'-e',renderer,json.dumps(settings)],capture_output=True,text=True,timeout=20)
                    self.assertEqual(result.returncode,0,result.stderr[-500:])
                    inspected=json.loads(result.stdout)
                finally:
                    # Chrome's launcher may exit while its helpers still own the
                    # profile. Stop the entire isolated session before cleanup.
                    try:os.killpg(process.pid,signal.SIGTERM)
                    except (ProcessLookupError,PermissionError):pass
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:os.killpg(process.pid,signal.SIGKILL)
                        except (ProcessLookupError,PermissionError):process.kill()
                        process.wait(timeout=5)
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except (ProcessLookupError,PermissionError):pass
                    for _ in range(100):
                        try:os.killpg(process.pid,0)
                        # macOS may leave unsignalable sandbox helper/zombie
                        # groups after the owned browser has exited.
                        except (ProcessLookupError,PermissionError):break
                        time.sleep(.02)
            self.assertEqual(inspected['width'],width)
            self.assertEqual(inspected['height'],height)
            self.assertFalse(inspected['overflow'])
            self.assertEqual(inspected['cards'],2)
            self.assertIn('159.00 USD',inspected['text'])
            self.assertTrue(image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
            renders.append(image)
        artifact_output=os.environ.get('SPIELOS_ACCEPTANCE_ARTIFACTS')
        if artifact_output:
            destination=Path(artifact_output);destination.mkdir(parents=True,exist_ok=True)
            for generated in [page,*renders]:shutil.copy2(generated,destination/generated.name)
        builder=BrandRegistry(self.root,self.owner)
        files=['voice.md','design-system/tokens.json','design-system/components.css','assets/example-mark.svg',
               'templates/report.html','examples/sales-report.html','examples/report-390.png','examples/report-1280.png']
        candidate=builder.candidate(version='synthetic-v1',files=files)
        with self.assertRaises(PermissionError):builder.release(candidate,inspection={})
        image=renders[-1]
        inspection={'candidate_digest':fingerprint(candidate),'render':image.relative_to(brand).as_posix(),
                    'render_digest':hashlib.sha256(image.read_bytes()).hexdigest(),
                    'observations':['Both real browser viewports contain two cards without horizontal overflow; values and business-outcome disclaimer are present.'],
                    'review_kind':'synthetic renderer acceptance; company identity approval is not implied'}
        reviewer=BrandRegistry(self.root,self.reviewer)
        release=reviewer.release(candidate,inspection=inspection)
        original=reviewer.resolve(release)['content']['design-system/components.css']
        (brand/'design-system/components.css').write_text('/* A later draft edit */')
        self.assertEqual(reviewer.resolve(release)['content']['design-system/components.css'],original)
        spec_path=self.root/'company/workflows/sales-report/workflow.json'
        spec=json.loads(spec_path.read_text());spec['brand_release']=release
        spec_path.write_text(json.dumps(spec))
        output=self.root.parent/(self.root.name+'-brand-export')
        self.addCleanup(lambda:shutil.rmtree(output,ignore_errors=True))
        exported=PortablePackages(self.root,self.owner).export_workflow('sales-report',output,package_id='branded-report')
        self.assertIn('brand/releases/'+release+'.json',exported['manifest']['files'])
        # The immutable release carries the actual approved assets even after
        # a mutable draft changes. Its digest travels with the package.
        bundled=json.loads((output/'content/brand/releases'/(release+'.json')).read_text())
        self.assertEqual(base64.b64decode(bundled['content']['design-system/components.css']),base64.b64decode(original))

    @scenario('branding.generic_declared_reference_roles','portability.pinned_closure_and_brand_export')
    def test_a_design_lead_versions_a_poster_system_through_cli_and_mcp_without_report_classes(self):
        import base64,hashlib,json,os,subprocess,sys
        from pathlib import Path
        from unittest.mock import patch
        from PIL import Image
        from company.branding import BrandRegistry
        from company.home import fingerprint
        from company.mcp import CompanySession
        from company.portability import PortablePackages
        brand=self.root/'company/brand'
        assets={
            'voice.md':'Use concise source-backed poster copy.',
            'design-system/night.css':':root {--poster-ink:#edf2fa;--poster-paper:#111827}',
            'design-system/scene-card.css':'.scene-card {color:var(--poster-ink);background:var(--poster-paper);padding:var(--poster-gutter,1rem)}',
            'design-system/references/mark.svg':'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><circle cx="4" cy="4" r="3"/></svg>',
            'templates/scene.html':'<!doctype html><title>Synthetic poster</title><article class="scene-card">Verified inputs only.</article>',
        }
        for name,text in assets.items():
            target=brand/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
        image=brand/'examples/poster-fixture.png'
        # This is a transport/snapshot unit fixture, not a visual quality claim.
        # Actual two-viewport browser/render quality is exercised separately.
        Image.new('RGB',(24,16),(17,24,39)).save(image)
        roles={'voice':['voice.md'],'tokens':['design-system/night.css'],'components':['design-system/scene-card.css'],
               'assets':['design-system/references/mark.svg'],'templates':['templates/scene.html'],'examples':['examples/poster-fixture.png']}
        contract=brand/'brand.json';contract.write_text(json.dumps({'schema':1,'roles':roles}))
        files=list(assets)+['examples/poster-fixture.png'];file_list=self.root/'brand-files.json';file_list.write_text(json.dumps(files))
        source=Path(__file__).resolve().parents[3]
        result=subprocess.run([sys.executable,'-B','-m','company','brand','candidate','--home',str(self.root),
            '--version','poster-v1','--files',str(file_list),'--json'],cwd=source,capture_output=True,text=True,
            env={**os.environ,'PYTHONPATH':str(source)},timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        candidate=json.loads(result.stdout)
        self.assertEqual(candidate['contract']['roles'],roles)
        self.assertIn('brand.json',candidate['files'])
        self.assertNotIn('design-system/tokens.json',candidate['files'])
        self.assertNotIn('design-system/components.css',candidate['files'])
        session=CompanySession();selected=session.select(str(self.root));args={'company_id':selected['company_id']}
        same=session.call('build_workflow',{**args,'action':'brand-candidate','payload':{'version':'poster-v1','files':files}})
        self.assertEqual(same,candidate)
        inspection={'candidate_digest':fingerprint(candidate),'render':'examples/poster-fixture.png',
                    'render_digest':hashlib.sha256(image.read_bytes()).hexdigest(),'observations':['Synthetic snapshot/API test only; actual visual qualification is a separate test.']}
        with self.assertRaises(PermissionError):session.call('review_output',{**args,'action':'brand-release','payload':{'candidate':candidate,'inspection':inspection}})
        token=self.authority.issue(self.owner,subject='poster-fixture-reviewer',roles=['reviewer'])
        with patch.dict(os.environ,{'SPIELOS_PRINCIPAL_TOKEN':token}):
            release=session.call('review_output',{**args,'action':'brand-release','payload':{'candidate':candidate,'inspection':inspection}})['brand_release']
        import shutil
        spec_path=self.root/'company/workflows/sales-report/workflow.json'
        packaged=json.loads(spec_path.read_text());packaged['brand_release']=release;spec_path.write_text(json.dumps(packaged))
        destination=self.root.parent/(self.root.name+'-poster-export')
        self.addCleanup(lambda:shutil.rmtree(destination,ignore_errors=True))
        exported=subprocess.run([sys.executable,'-B','-m','company','export','sales-report','--home',str(self.root),
            '--out',str(destination),'--package-id','poster-aware','--version','poster-202610','--json'],cwd=source,
            capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(source)},timeout=10)
        self.assertEqual(exported.returncode,0,exported.stderr)
        self.assertEqual(json.loads(exported.stdout)['manifest']['version'],'poster-202610')
        self.assertTrue((destination/'content/brand/design-system/night.css').is_file())
        original=(brand/'design-system/scene-card.css').read_bytes()
        (brand/'design-system/scene-card.css').write_text('.a-new-unapproved-draft {color:red}')
        pinned=BrandRegistry(self.root,self.owner).resolve(release)
        self.assertEqual(base64.b64decode(pinned['content']['design-system/scene-card.css']),original)
        spec=specification('host');spec['version']='poster-aware';spec['brand_release']=release
        spec['execution']['brand_context']=['voice.md','design-system/night.css','design-system/scene-card.css']
        workflow=self.runtime.candidate(spec);resolved=self.runtime.manifest(workflow)
        self.assertEqual(resolved['resolved_brand']['digest'],release)
        self.assertEqual(resolved['resolved_context']['brand/design-system/scene-card.css']['text'],original.decode())
        self.assertEqual(resolved['resolved_brand']['context_files'],sorted(spec['execution']['brand_context']))
        self.assertNotIn('brand/templates/scene.html',resolved['resolved_context'])
        self.assertNotIn('brand/brand.json',resolved['resolved_context'])
        invalid=deepcopy(spec);invalid['version']='absent-brand-context';invalid['execution']['brand_context']=['not-pinned.css']
        with self.assertRaisesRegex(ValueError,'pinned file'):self.runtime.candidate(invalid)
        # Missing roles or unpinned references fail without executing anything.
        registry=BrandRegistry(self.root,self.owner)
        with self.assertRaisesRegex(ValueError,'included'):registry.candidate(version='missing-example',files=list(assets))
        bad={'schema':1,'roles':{**roles,'assets':['../outside.svg']}};contract.write_text(json.dumps(bad))
        with self.assertRaises(ValueError):registry.candidate(version='escape',files=files+['../outside.svg'])

    @scenario('reporting.business_measurement_contract')
    def test_business_readings_need_population_window_units_and_honest_baseline(self):
        from copy import deepcopy
        from company.observability.read_model import record_outcome,workflow_scorecard
        release=self.runtime.candidate(specification())
        observation={'metric_id':'repeat-purchase-rate','name':'Repeat purchase rate','definition':'Share of identified customers who purchased again during the stated window',
            'unit':'fraction','direction':'increase','population':'Synthetic customers with a complete 30-day observation window',
            'window_start':'2026-01-01T00:00:00+00:00','window_end':'2026-02-01T00:00:00+00:00',
            'value':0.2,'sample_size':5,'minimum_sample_size':30,'minimum_reason':'The owner-agreed pilot requires at least 30 complete customer windows',
            'source':'Synthetic fixture, not a real business result','baseline':{'state':'unknown','reason':'No earlier comparable window'},'release_digest':release}
        recorded=record_outcome(self.runtime,observation)
        self.assertEqual(recorded['state'],'insufficient_evidence')
        self.assertEqual(recorded['baseline']['state'],'unknown')
        self.assertIn('causal impact is not established',recorded['attribution'])
        for field in ('population','unit','direction','window_start','minimum_reason'):
            invalid=deepcopy(observation);invalid.pop(field)
            with self.subTest(field=field):
                with self.assertRaises(ValueError):record_outcome(self.runtime,invalid)
        invalid=deepcopy(observation);invalid['baseline']={'state':'observed','value':0}
        with self.assertRaises(ValueError):record_outcome(self.runtime,invalid)
        unknown=deepcopy(observation);unknown.update(value=None,unknown_reason='No verified reading yet',sample_size=0)
        self.assertEqual(record_outcome(self.runtime,unknown)['state'],'unknown')
        card=workflow_scorecard(self.runtime)
        self.assertEqual(card['business_outcomes']['state'],'recorded')
        self.assertEqual(card['runs']['accepted_outputs'],0)

    @scenario('evaluation.model_judge_contract_and_calibration')
    def test_a_builder_cannot_fabricate_calibration_review_identities(self):
        from company.evals.contracts import record_judge_calibration
        from company.workflows.runs import digest
        spec=specification();release=self.runtime.candidate(spec)
        runs=[]
        for case in spec['evaluation']['cases'][:2]:
            runs.append(self.runtime.run(release,case['input'],request_key='calibration:'+case['id'],candidate_case=case['id']))
        judge={'model':'synthetic-judge','prompt_digest':digest('Synthetic editorial anchors'),'version':'synthetic-judge-v1'}
        ratings=[{'run_id':runs[0]['id'],'human_state':'pass','judge_state':'pass','judge_source':'Synthetic judge fixture A'},
                 {'run_id':runs[1]['id'],'human_state':'fail','judge_state':'fail','judge_source':'Synthetic judge fixture B'}]
        with self.assertRaises(PermissionError):record_judge_calibration(self.runtime,judge=judge,ratings=ratings,reason='Self-signed')
        record=record_judge_calibration(self.review_runtime,judge=judge,ratings=ratings,reason='Synthetic independent calibration acceptance; not a creative quality certificate')
        proposed=specification();proposed['version']='judge-1'
        proposed['evaluation']['criteria'].append({'id':'editorial','question':'Does the output satisfy the reviewed editorial examples?','dimension':'output','evaluator':'model','severity':'block','source':'Pinned editorial brief',
            'anchors':{'pass':'The title identifies the reporting period','fail':'The title obscures the reporting period'},'judge':{**judge,'calibration_id':'forged'}})
        with self.assertRaisesRegex(ValueError,'authenticated'):self.runtime.candidate(proposed)
        proposed['evaluation']['criteria'][-1]['judge']['calibration_id']=record['calibration_id']
        candidate=self.runtime.candidate(proposed)
        actual=self.runtime.manifest(candidate)['evaluation']['criteria'][-1]['judge']['calibration']
        self.assertEqual(actual[0]['human_reviewer'],self.reviewer.subject)
        self.assertEqual(actual[0]['artifact_digest'],digest(runs[0]['output']))
