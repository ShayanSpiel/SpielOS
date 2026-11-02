"""Isolated desktop plugin entrypoint; data never belongs to this package."""
import sys
if sys.version_info < (3,11):
    print('SpielOS needs Python 3.11 or newer. Run the Setup skill for help.',file=sys.stderr)
    raise SystemExit(1)
for stream in (sys.stdin,sys.stdout,sys.stderr):
    if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
import argparse
import json
import os
os.environ.setdefault('PYTHONUTF8','1')
from pathlib import Path

root=Path(__file__).resolve().parents[1]
runtime=root/'runtime'
if not (runtime/'company/cli.py').is_file():
    print('This SpielOS plugin is incomplete. Install the packaged desktop release, then run setup.',file=sys.stderr)
    raise SystemExit(1)
sys.path.insert(0,str(runtime))
if sys.argv[1:2] == ['onboarding']:
    parser=argparse.ArgumentParser(description='Read or record explicit company onboarding choices.')
    parser.add_argument('action',choices=('status','local','connect-request','tour-shown'))
    parser.add_argument('--home',required=True);parser.add_argument('--report-url')
    args=parser.parse_args(sys.argv[2:])
    from company.onboarding import status,choose,tour_shown,_runtime
    selected=_runtime(args.home)
    result=status(selected.home) if args.action=='status' else tour_shown(selected.home,args.report_url) if args.action=='tour-shown' else choose(selected.home,'connect' if args.action=='connect-request' else 'local')
    print(json.dumps(result));raise SystemExit(0)
if sys.argv[1:2] == ['setup-local-capture']:
    parser=argparse.ArgumentParser(description='Enable private local company activity and bounded reviews; never connect an exporter.')
    parser.add_argument('--home',required=True)
    args=parser.parse_args(sys.argv[2:])
    from company.mcp import CompanySession
    selected=CompanySession();info=selected.select(args.home)
    company=selected.runtime(info['company_id']);company._actor('configure')
    policy=company.home/'.spielos/telemetry.json'
    if policy.is_symlink():raise PermissionError('Activity policy cannot be a symbolic link')
    created=False
    try:
        with os.fdopen(os.open(policy,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as output:
            json.dump({'enabled':False,'payload_policy':'reviewed_evidence',
                'automatic':{'enabled':True,'judge_runtime':'selected_host'},
                'capture_scope':'Local supplied context, exposed tool events, final answers and usage; no hidden reasoning. Export disabled.'},output,indent=2)
            output.write('\n')
        created=True
    except FileExistsError:pass
    config=json.loads(policy.read_text())
    print(json.dumps({'created':created,'existing_policy_preserved':not created,
        'local_capture':config.get('payload_policy')=='reviewed_evidence',
        'bounded_review':config.get('automatic',{}).get('enabled') is True,
        'export_enabled':config.get('enabled') is True,
        'hooks':'Open this company as the workspace and review hooks in the host; setup does not grant trust.'}))
    raise SystemExit(0)
from company.cli import main
raise SystemExit(main())
