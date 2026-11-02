"""Visible company content and an explicit, recoverable lean-layout migration.

Migration moves approved paths; it does not copy production content, remove
history or run work. Compatibility aliases keep old references resolving while
callers move to logical owner paths. They are recorded, not a second data store.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import uuid
from .platform import create_alias,is_link,protect_private

OWNER_LAYERS = ('departments','skills','capabilities','connections','strategy','brand','agents/installed')
VISIBLE_LAYERS = ('strategy','brand','workflows','agents','skills','connections','departments')
RUNTIME_FILES = {'__init__.py','core.py'}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_digest(path):
    path=Path(path)
    value=hashlib.sha256()
    if is_link(path):
        return hashlib.sha256(os.readlink(path).encode()).hexdigest()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            value.update(block)
    return value.hexdigest()


def inventory(path, *, home):
    path,home=Path(path),Path(home).resolve()
    entries={}
    items=[path] if path.is_file() or is_link(path) else sorted(path.rglob('*'))
    for item in items:
        if not item.is_file() and not is_link(item):continue
        if is_link(item) and not item.resolve().is_relative_to(home):
            raise ValueError(f'External link must be resolved before migration: {item.relative_to(home)}')
        key='.' if item==path else item.relative_to(path).as_posix()
        entries[key]={'sha256':file_digest(item),'kind':'link' if is_link(item) else 'file'}
    return entries


def write_json(path,value):
    """Atomic local metadata replacement; no preservation copy."""
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.pending')
    descriptor=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
        stream.write(json.dumps(value,indent=2)+'\n')
        stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    protect_private(path)


def legacy_inventory(root):
    """Read a fresh WAL-aware snapshot without changing historical lineage."""
    import sqlite3
    path=Path(root)/'.spielos/state/company.sqlite'
    if not path.is_file():return None
    source=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    snapshot=sqlite3.connect(':memory:');snapshot.row_factory=sqlite3.Row
    try:
        source.backup(snapshot)
        tables={row[0] for row in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        result={'schema':1,'policy':'read_only; no pending work or external approval is resumed','tables':{}}
        for table in ('core_goals','core_goal_metadata','core_goal_edges','core_runs','core_interventions','core_work_orders','core_memory','core_approvals','core_workflows','core_workflow_runs','core_notifications','core_evidence'):
            if table not in tables:continue
            records=[]
            for row in snapshot.execute('SELECT * FROM '+table+' ORDER BY rowid'):
                record=dict(row)
                records.append({key:record[key] for key in ('id','name','status','scope','goal_id','workflow_id') if key in record} | {'sha256':fingerprint(record)})
            result['tables'][table]=records
        return result
    finally:source.close();snapshot.close()


def migrate_legacy_context(root,expected):
    """Preferences keep owner scope. Other claims require explicit mapping."""
    import sqlite3
    from .security import CompanyAuthority
    if expected is None:return {'owner_preferences':0,'deferred_claims':0}
    if legacy_inventory(root)!=expected:
        raise ValueError('Legacy work changed after preview; review its current state before importing context')
    authority=CompanyAuthority(root);authority.bootstrap();owner=authority.local_owner()
    source=sqlite3.connect((Path(root)/'.spielos/state/company.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
    source.row_factory=sqlite3.Row
    try:rows=[dict(row) for row in source.execute("SELECT * FROM core_memory WHERE scope='owner' AND status='active' ORDER BY created_at")]
    finally:source.close()
    if rows:
        from .workflows.runs import WorkflowRuntime
        runtime=WorkflowRuntime(Path(root)/'.spielos/state/workflows.sqlite',home=root,principal=owner)
        with runtime.connect() as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS workflow_memory_origins (memory_id TEXT PRIMARY KEY REFERENCES workflow_memories(id),origin_json TEXT NOT NULL)')
            for row in rows:
                identity='legacy-owner-'+fingerprint({'id':row['id']})[:32]
                if connection.execute('SELECT id FROM workflow_memories WHERE id=?',(identity,)).fetchone():continue
                connection.execute('INSERT INTO workflow_memories(id,scope,workflow_id,claim,evidence_json,source,actor,created_at,status) VALUES(?,?,?,?,?,?,?,?,?)',
                    (identity,'owner',None,row['claim'],'[]','Preserved explicit owner preference; original lineage remains in read-only history',owner.subject,row['created_at'],'active'))
                connection.execute('INSERT INTO workflow_memory_origins VALUES(?,?)',(identity,canonical({'table':'core_memory','record':row,'original_authority':'historical; not upgraded to an authenticated approval'})))
                runtime._audit(connection,'legacy_owner_preference',identity,{'legacy_id':row['id'],'claim_digest':fingerprint(row['claim'])},actor=owner.subject)
    deferred=[row for row in expected['tables'].get('core_memory',[]) if row.get('scope')!='owner' and row.get('status')=='active']
    write_json(Path(root)/'.spielos/legacy-review.json',{'schema':1,'inventory':expected,
        'owner_preferences_imported':len(rows),'deferred_memory_claims':deferred,
        'policy':'Owner preferences retain owner scope. Workflow and strategy claims retain their historical lineage until an explicit workflow or Improvement mapping is reviewed. Old approvals grant no new action authority.'})
    return {'owner_preferences':len(rows),'deferred_claims':len(deferred)}


class CompanyHome:
    def __init__(self,root):
        self.root=Path(root).expanduser().resolve()
        self.layout_path=self.root/'.spielos/layout.json'

    @property
    def lean(self):
        if not self.layout_path.is_file():return False
        data=json.loads(self.layout_path.read_text())
        if data.get('schema')!=2:raise ValueError('Unsupported company layout version')
        return True

    @property
    def content(self):
        return self.root/'company' if self.lean else self.root/'.agents/company'

    @property
    def runtime(self):
        return self.root/'.spielos/runtime/company' if self.lean else self.root/'.agents/company'

    def require_destination(self):
        from .runtime.paths import validate_home_destination
        validate_home_destination(self.root)
        for name in ('company','.spielos'):
            path=self.root/name
            if is_link(path) or not path.resolve().is_relative_to(self.root):
                raise ValueError('Company content and private state must remain inside the selected home')

    def require_ready(self):
        for journal in (self.root/'.spielos/imports').glob('*/journal.json'):
            if is_link(journal) or json.loads(journal.read_text()).get('status')!='complete':
                raise ValueError('A package installation needs recovery before using company definitions')

    def owner_path(self,layer):
        if layer not in OWNER_LAYERS and layer!='workflows':
            raise ValueError('Unknown company content layer')
        return self.content/('connections/legacy-capabilities' if self.lean and layer=='capabilities' else layer)

    def migration_plan(self):
        self.require_destination()
        if self.lean:return {'schema':1,'home':str(self.root),'already_migrated':True,'moves':[]}
        old=self.root/'.agents/company'
        if not (old/'__main__.py').is_file():
            raise ValueError('Select an installed company home before migrating')
        if is_link(old):raise ValueError('Unrecognized runtime link; inspect the home before migrating')
        destination=self.root/'.spielos/runtime/company'
        if destination.exists():raise ValueError('Runtime destination already exists; resume the recorded migration instead')
        moves=[]
        for layer in OWNER_LAYERS:
            base=old/layer
            if not base.is_dir():continue
            for item in sorted(base.iterdir()):
                if item.name in RUNTIME_FILES or item.name=='__pycache__':continue
                # Runtime-owned files are identified by the installation receipt.
                receipt=self.root/'.spielos/vendored.json'
                shipped=set(json.loads(receipt.read_text()).get('files',{}).get('agents',[])) if receipt.is_file() else set()
                relative=item.relative_to(self.root/'.agents').as_posix()
                if relative in shipped:continue
                if not receipt.is_file() and item.is_file() and not is_link(item):
                    from .runtime.bootstrap import template_root
                    template=template_root()/'agents'/relative
                    if template.is_file() and file_digest(template)==file_digest(item):continue
                target=self.root/'company'/('connections/legacy-capabilities' if layer=='capabilities' else layer)/item.name
                if target.exists() or is_link(target):
                    raise ValueError(f'Owner path collision: {target.relative_to(self.root)}')
                if is_link(item):
                    raise ValueError(f'Owner package link needs an explicit rebase: {item.relative_to(self.root)}')
                entries=inventory(item,home=self.root)
                # Relative links that leave the moved package require an explicit
                # rebase decision; never silently change their meaning.
                for link in ([item] if is_link(item) else item.rglob('*')):
                    if is_link(link) and not os.path.isabs(os.readlink(link)) and not link.resolve().is_relative_to(item.resolve() if item.is_dir() else item.parent.resolve()):
                        raise ValueError(f'Relative link needs an explicit rebase: {link.relative_to(self.root)}')
                moves.append({'from':item.relative_to(old).as_posix(),'to':target.relative_to(self.root).as_posix(),
                              'inventory':entries,'inventory_digest':fingerprint(entries)})
        return {'schema':1,'home':str(self.root),'runtime_from':'.agents/company',
                'runtime_to':'.spielos/runtime/company','moves':moves,
                'history_policy':'preserve_read_only','external_actions':'never_replay',
                'compatibility':'recorded internal aliases; no copied owner data','legacy_state':legacy_inventory(self.root)}

    def apply_migration(self,plan,*,expected_digest,after_operation=None):
        self.require_destination()
        if fingerprint(plan)!=expected_digest or plan.get('home')!=str(self.root):
            raise ValueError('Migration must match the exact reviewed plan and company')
        if plan.get('already_migrated'):
            if not self.lean:raise ValueError('Migration state changed')
            return {'already_migrated':True,'moved':0}
        journal_path=self.root/'.spielos/migration.json'
        if journal_path.exists():
            journal=json.loads(journal_path.read_text())
            if journal.get('plan_digest')!=expected_digest:raise ValueError('Another migration is already recorded')
        else:
            current=self.migration_plan()
            if fingerprint(current)!=expected_digest:raise ValueError('Company changed since migration preview')
            journal={'schema':1,'plan_digest':expected_digest,'plan':plan,'completed':[],'status':'applying'}
            write_json(journal_path,journal)
        old=self.root/'.agents/company'
        runtime=self.root/'.spielos/runtime/company'
        if is_link(old) and old.resolve()!=runtime.resolve():
            raise ValueError('Runtime alias changed after preview')
        if not runtime.exists():
            runtime.parent.mkdir(parents=True,exist_ok=True)
            old.rename(runtime)
        if not is_link(old):
            if old.exists():raise ValueError('Runtime compatibility path is occupied')
            create_alias(old,runtime)
        for index,operation in enumerate(plan['moves']):
            relative=Path(operation['from']);target_relative=Path(operation['to'])
            expected_target=(Path('company/connections/legacy-capabilities')/Path(*relative.parts[1:]) if relative.parts and relative.parts[0]=='capabilities' else Path('company')/relative)
            if relative.is_absolute() or '..' in relative.parts or target_relative!=expected_target:
                raise ValueError('Migration operation escapes its approved owner layer')
            if not any(relative==Path(layer) or Path(layer) in relative.parents for layer in OWNER_LAYERS):
                raise ValueError('Migration operation is outside owner content')
            source=runtime/relative;target=self.root/target_relative
            if not source.parent.resolve().is_relative_to(runtime.resolve()):
                raise ValueError('Migration source parent escaped the runtime')
            if not target.parent.resolve().is_relative_to(self.root):
                raise ValueError('Migration destination parent escaped the company')
            if target.exists() and (is_link(source) or (source.exists() and source.samefile(target))):
                if source.resolve()!=target.resolve():raise ValueError('Compatibility link points to a different destination')
            elif target.exists() and not source.exists():
                # Crash after rename, before recording the alias.
                if fingerprint(inventory(target,home=self.root))!=operation['inventory_digest']:
                    raise ValueError('Moved content changed before recovery')
                create_alias(source,target)
            else:
                if target.exists() or is_link(source):raise ValueError('Migration destination changed')
                if fingerprint(inventory(source,home=self.root))!=operation['inventory_digest']:
                    raise ValueError('Owner content changed after preview')
                target.parent.mkdir(parents=True,exist_ok=True)
                source.rename(target)
                create_alias(source,target)
            if index not in journal['completed']:
                journal['completed'].append(index);write_json(journal_path,journal)
            if after_operation:after_operation(index)
        self.initialize_content(company_id=journal.get('company_id'))
        from .security import CompanyAuthority
        CompanyAuthority(self.root).bootstrap()
        journal['context_migration']=migrate_legacy_context(self.root,plan.get('legacy_state'))
        journal['status']='complete';write_json(journal_path,journal)
        return {'already_migrated':False,'moved':len(plan['moves']),'plan_digest':expected_digest,
                'owner_files':sum(len(row['inventory']) for row in plan['moves'])}

    def initialize_content(self,*,company_id=None):
        self.require_destination()
        if self.layout_path.exists():
            current=json.loads(self.layout_path.read_text())
            company_id=current['company_id']
        else:company_id=company_id or 'company-'+uuid.uuid4().hex
        content=self.root/'company'
        for layer in VISIBLE_LAYERS:
            if not (content/layer).resolve().is_relative_to(content.resolve()):
                raise ValueError('Company layer escaped owner content')
            (content/layer).mkdir(parents=True,exist_ok=True)
        for name in ('assets','design-system','templates','examples'):
            (content/'brand'/name).mkdir(parents=True,exist_ok=True)
        (content/'agents/installed').mkdir(parents=True,exist_ok=True)
        # Generic draft assets are additive; an update never replaces owner edits.
        # Source and installed runtime find the same shipped home templates.
        from .runtime.bootstrap import template_root
        templates=template_root()/'home'
        if templates.is_dir():
            for path in sorted(templates.rglob('*')):
                if not path.is_file():continue
                target=content/path.relative_to(templates)
                if target.exists() or is_link(target):continue
                if not target.parent.resolve().is_relative_to(content.resolve()):
                    raise ValueError('Company template path escaped owner content')
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(path.read_bytes())
        # Owner documents are created only when absent. Updates never replace them.
        documents={
            'README.md':'# Company\n\nEditable company context lives here. Runtime code is in .spielos/runtime/.\nProfile, strategy, brand, workflows, reusable agents, skills, connections and optional Departments have distinct ownership.\n',
            'profile.md':'# Company profile\n\nStatus: needs owner input. Unknown facts remain unknown.\n\n## Company\n\nUnknown.\n\n## Intended customers\n\nUnknown.\n\n## Accountable owner\n\nUnknown.\n\n## Responsibilities\n\nUnknown.\n\n## Boundaries\n\nUnknown.\n',
            'strategy/README.md':'# Strategy\n\nRecord explicit owner direction and outcome windows. Operational expression and approved examples belong in brand/.\n',
            'brand/README.md':'# Brand infrastructure\n\nOwner-owned tokens, components, assets, templates, voice and examples live here. A release pins their actual content digests. A draft or missing reference cannot authorize production output.\n',
            'brand/voice.md':'# Voice\n\nStatus: draft, needs owner review.\n\nUse clear concrete language. Record approved examples and unacceptable variations before releasing a workflow.\n',
            'workflows/README.md':'# Workflows\n\nEach workflow owns workflow.json, brief.md, execution/, evaluation/rubric.json, evaluation/cases/ and example outputs. Drafts need both harnesses before release.\n',
            'connections/README.md':'# Connections\n\nStore non-secret declarations and credential references only. Actual secrets stay in the host connection store or private environment.\n'}
        for name,text in documents.items():
            path=content/name
            if not path.exists():path.write_text(text)
        if not self.layout_path.exists():
            write_json(self.layout_path,{'schema':2,'company_id':company_id,'content':'company',
                'runtime':'.spielos/runtime/company','legacy_history':'read_only',
                'compatibility_alias':'.agents/company'})
        return {'company_id':company_id,'content':str(content),'runtime':str(self.root/'.spielos/runtime/company')}


class CompanyProfile:
    """Typed owner facts in one readable Markdown document, not two stores."""
    SECTIONS={'name':'Company','audience':'Intended customers','owner':'Accountable owner',
              'responsibilities':'Responsibilities','boundaries':'Boundaries'}

    def __init__(self,home,principal):
        from .security import CompanyAuthority
        self.home=CompanyHome(home);self.authority=CompanyAuthority(home)
        self.principal=principal;self.authority.authorize(principal,'read')
        self.path=self.home.content/'profile.md'
        if is_link(self.path) or not self.path.resolve().is_relative_to(self.home.content):
            raise ValueError('Company profile must remain in its selected home')

    def read(self):
        import re
        self.authority.authorize(self.principal,'read')
        text=self.path.read_text();fields={};missing=[]
        for key,title in self.SECTIONS.items():
            values=re.findall(r'^## '+re.escape(title)+r'\s*\n(.*?)(?=^## |\Z)',text,re.M|re.S)
            if len(values)>1:raise ValueError('Profile has duplicate '+title+' sections; resolve the ambiguity explicitly')
            content=values[0].strip() if values else ''
            unknown=not content or content.lower().rstrip('.') in {'unknown','needs owner input'}
            if unknown:fields[key]=None;missing.append(key)
            elif key in {'responsibilities','boundaries'}:fields[key]=[line.removeprefix('- ').strip() for line in content.splitlines() if line.strip()]
            else:fields[key]=content
        return {'schema':1,'fields':fields,'state':'needs_owner_input' if missing else 'provided',
                'missing_fields':missing,'source':'company/profile.md','sha256':hashlib.sha256(self.path.read_bytes()).hexdigest()}

    def update(self,fields,*,source,runtime):
        import re
        actor=self.authority.authorize(self.principal,'configure')
        if not isinstance(fields,dict) or not fields or set(fields)-set(self.SECTIONS) or not isinstance(source,str) or not source.strip():
            raise ValueError('Profile updates need explicit owner facts and their source')
        text=self.path.read_text();before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        existing=self.read() # Reject ambiguous duplicate sections before changing anything.
        for key,value in fields.items():
            if key in {'responsibilities','boundaries'}:
                if not isinstance(value,list) or not value or any(not isinstance(item,str) or not item.strip() or '\n' in item for item in value):
                    raise ValueError('Responsibilities and boundaries need explicit lists')
                body='\n'.join('- '+item.strip() for item in value)
            else:
                if not isinstance(value,str) or not value.strip() or '\n' in value:raise ValueError('Profile identity fields need explicit single-line text')
                body=value.strip()
            if len(body)>4000:raise ValueError('Profile field exceeds the bounded context size')
            heading='## '+self.SECTIONS[key]
            pattern=r'^'+re.escape(heading)+r'\s*\n.*?(?=^## |\Z)'
            replacement=heading+'\n\n'+body+'\n\n'
            text=re.sub(pattern,lambda match:replacement,text,flags=re.M|re.S) if re.search(pattern,text,re.M|re.S) else text.rstrip()+'\n\n'+replacement
        complete=all(({**existing['fields'],**fields}).values())
        label='Status: owner facts provided.' if complete else 'Status: needs owner input.'
        text=re.sub(r'^Status:.*$',label,text,flags=re.M).rstrip()+'\n'
        after=hashlib.sha256(text.encode()).hexdigest()
        if runtime.home!=self.home.root:raise PermissionError('Profile audit belongs to another company')
        # The receipt records the exact file transition and explicit actor; it
        # does not infer preferences, strategy or a brand approval.
        with runtime.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if hashlib.sha256(self.path.read_bytes()).hexdigest()!=before:raise ValueError('Profile changed during the update; read the current owner document before retrying')
            runtime._audit(connection,'profile_update','company/profile.md',{'before':before,'after':after,'fields':sorted(fields),'source':source},actor=actor)
            temporary=self.path.with_name('profile.'+uuid.uuid4().hex+'.pending')
            temporary.write_text(text);os.replace(temporary,self.path)
        return self.read()
