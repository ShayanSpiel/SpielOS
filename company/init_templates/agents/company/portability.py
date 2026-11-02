"""Declarative, hash-bound package transfer; importing never executes package code."""
from pathlib import Path
import hashlib,json,os,re,shutil,uuid
from .home import CompanyHome,canonical,fingerprint,write_json
from .security import CompanyAuthority

LAYERS={'workflows','skills','agents','connections','departments','strategy','brand'}


def safe_name(name):
    if not isinstance(name,str) or not name or '\\' in name:raise ValueError('Invalid package path')
    path=Path(name)
    if path.is_absolute() or '..' in path.parts or path.as_posix()!=name or path.parts[0] not in LAYERS:
        raise ValueError('Package paths must stay in explicit owner layers')
    if any(part.startswith('.') or part in {'__pycache__','node_modules'} for part in path.parts):
        raise ValueError('Private state and hidden files cannot enter a portable package')
    if path.parts[0]=='agents' and (len(path.parts)!=3 or path.parts[1]!='installed' or path.suffix!='.json'):
        raise ValueError('Only declarative agent records are portable')
    if path.parts[0]=='connections' and path.suffix!='.json':raise ValueError('Connections must be non-secret declarations')
    return path


def digest_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package_inventory(folder,manifest):
    folder=Path(folder).resolve()
    if manifest.get('schema')!=1 or not re.fullmatch(r'[a-z][a-z0-9-]{0,62}',str(manifest.get('id',''))) or not isinstance(manifest.get('version'),str) or not manifest['version']:
        raise ValueError('Package needs a versioned portable identity')
    files=manifest.get('files')
    if not isinstance(files,dict) or not files:raise ValueError('Package file inventory is empty')
    if len(files)>10000:raise ValueError('Package exceeds the bounded file inventory')
    total=0
    for name,expected in files.items():
        relative=safe_name(name);path=folder/'content'/relative
        if not isinstance(expected,str) or not re.fullmatch(r'[0-9a-f]{64}',expected):raise ValueError('Package requires actual content digests')
        if path.is_symlink() or not path.resolve().is_relative_to(folder/'content') or not path.is_file():raise ValueError('Package contains an absent, external or symbolic-link file')
        total+=path.stat().st_size
        if total>128*1024*1024:raise ValueError('Package exceeds 128 megabytes')
        if digest_file(path)!=expected:raise ValueError('Package content changed: '+name)
        if relative.parts[0]=='connections':
            declaration=json.loads(path.read_text())
            if not isinstance(declaration,dict) or set(declaration)-{'id','provider','credential_ref','permissions'} or not declaration.get('credential_ref'):
                raise ValueError('Portable connections contain credential references, never credentials')
    # Unlisted payloads cannot hide credentials or executable install hooks.
    actual={path.relative_to(folder/'content').as_posix() for path in (folder/'content').rglob('*') if path.is_file() or path.is_symlink()}
    if actual!=set(files):raise ValueError('Package contains unlisted payload files')
    return files


class PortablePackages:
    def __init__(self,home,principal):
        self.home=CompanyHome(home);self.authority=CompanyAuthority(home)
        self.principal=principal;self.authority.authorize(principal,'read')

    def export_workflow(self,identity,destination,*,package_id,version='1'):
        self.authority.authorize(self.principal,'export');self.home.require_ready()
        from .commands.workflows import read_package
        from .agents.loader import AgentCatalog
        from .branding import BrandRegistry
        source=self.home.content/'workflows'/identity
        spec=read_package(self.home.root,source/'workflow.json')
        paths={path.relative_to(self.home.content).as_posix() for path in source.rglob('*') if path.is_file() or path.is_symlink()}
        paths.update(spec.get('dependencies',{}));paths.update(spec.get('context_versions',{}))
        if spec['execution']['provider']=='host':
            binding=spec['execution']['binding']
            if not binding.startswith('agent:'):raise ValueError('Host dependency is not declarative')
            declaration,revisions=AgentCatalog(self.home.root,self.principal).resolve(binding.removeprefix('agent:'))
            paths.update(revisions)
            for skill in declaration['skill_ids']:
                paths.update(path.relative_to(self.home.content).as_posix() for path in (self.home.content/'skills'/skill).rglob('*') if path.is_file())
            for connection in declaration['connection_ids']:paths.add('connections/'+connection+'.json')
        brand=None
        if spec.get('brand_release'):
            brand=BrandRegistry(self.home.root,self.principal).resolve(spec['brand_release'])
            paths.update('brand/'+name for name in brand['files'])
            paths.add('brand/releases/'+spec['brand_release']+'.json')
        payload={}
        for name in sorted(paths):
            relative=safe_name(name);path=self.home.content/relative
            if path.is_symlink() or not path.resolve().is_relative_to(self.home.content) or not path.is_file():
                raise ValueError('Portable dependency is missing or external: '+name)
            payload[name]=path.read_bytes()
        if brand is not None:
            import base64
            for name,encoded in brand['content'].items():
                payload['brand/'+name]=base64.b64decode(encoded,validate=True)
        target=Path(destination).expanduser().resolve()
        if target.exists() and any(target.iterdir()):raise FileExistsError('Export destination must be empty')
        if target.is_relative_to(self.home.root):raise ValueError('Export into a separately selected folder')
        manifest={'schema':1,'id':package_id,'version':version,'workflows':[identity],
                  'files':{name:hashlib.sha256(content).hexdigest() for name,content in payload.items()},
                  'source_company':self.authority.company_id,'policy':'definitions only; recipient reviews code, context and brand before release'}
        # Validate names, secrets and closure before writing the public result.
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}',package_id):raise ValueError('Invalid package identity')
        for name,content in payload.items():
            if name.startswith('connections/'):
                value=json.loads(content)
                if set(value)-{'id','provider','credential_ref','permissions'}:raise ValueError('Connection includes private values')
        target.mkdir(parents=True,exist_ok=True)
        for name,content in payload.items():
            path=target/'content'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
        write_json(target/'package.json',manifest)
        package_inventory(target,manifest)
        return {'manifest':manifest,'digest':fingerprint(manifest),'destination':str(target)}

    def preview(self,folder):
        self.authority.authorize(self.principal,'build');self.home.require_destination()
        folder=Path(folder).expanduser().resolve()
        manifest=json.loads((folder/'package.json').read_text())
        files=package_inventory(folder,manifest)
        actions=[]
        for name,expected in files.items():
            target=self.home.content/safe_name(name)
            if target.is_symlink() or not target.resolve().is_relative_to(self.home.content):raise ValueError('Destination escaped company ownership')
            if target.exists():
                if not target.is_file() or digest_file(target)!=expected:raise FileExistsError('Owner content collision: '+name)
                disposition='reuse_owner_file'
            else:disposition='install_new_file'
            actions.append({'path':name,'sha256':expected,'action':disposition})
        plan={'schema':1,'company_id':self.authority.company_id,'home':str(self.home.root),'source':str(folder),
              'package':manifest,'package_digest':fingerprint(manifest),'actions':actions,
              'execution':'never during import','approval':'definitions remain drafts; no effects or provider calls'}
        return {'plan':plan,'digest':fingerprint(plan)}

    def install(self,plan,*,expected_digest,after_operation=None):
        actor=self.authority.authorize(self.principal,'build');self.home.require_destination()
        if fingerprint(plan)!=expected_digest or plan.get('home')!=str(self.home.root) or plan.get('company_id')!=self.authority.company_id:
            raise ValueError('Install requires the exact reviewed plan for this company')
        transaction=self.home.root/'.spielos/imports'/expected_digest
        journal_path=transaction/'journal.json'
        if journal_path.exists():
            journal=json.loads(journal_path.read_text())
            if journal['plan_digest']!=expected_digest:raise ValueError('Import journal changed')
            if journal['status']=='complete':return journal['receipt']
        else:
            if self.preview(plan['source'])['digest']!=expected_digest:raise ValueError('Package or company changed after preview')
            self.home.require_ready()
            transaction.mkdir(parents=True,exist_ok=True)
            journal={'schema':1,'plan_digest':expected_digest,'status':'staging','completed':[],'actor':actor}
            write_json(journal_path,journal)
        stage=transaction/'stage'
        if journal['status']=='staging':
            # Recheck the complete source before resuming an interrupted stage.
            package_inventory(plan['source'],plan['package'])
            for operation in plan['actions']:
                if operation['action']!='install_new_file':continue
                name=operation['path'];path=stage/name
                path.parent.mkdir(parents=True,exist_ok=True)
                if not path.exists():path.write_bytes((Path(plan['source'])/'content'/name).read_bytes())
                if digest_file(path)!=operation['sha256']:raise ValueError('Staged package changed')
            journal['status']='applying';write_json(journal_path,journal)
        for index,operation in enumerate(plan['actions']):
            name=operation['path'];target=self.home.content/safe_name(name)
            if target.is_symlink() or not target.parent.resolve().is_relative_to(self.home.content):raise ValueError('Import destination changed')
            if operation['action']=='reuse_owner_file':
                if not target.is_file() or digest_file(target)!=operation['sha256']:raise ValueError('Reused owner content changed')
            elif index not in journal['completed']:
                staged=stage/name
                if target.exists():
                    if (not target.is_file() or digest_file(target)!=operation['sha256']
                            or staged.exists() and not os.path.samefile(staged,target)):
                        raise FileExistsError('Import destination changed')
                else:
                    if not staged.is_file() or digest_file(staged)!=operation['sha256']:raise ValueError('Staged package changed')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    os.link(staged,target) # exclusive create, never overwrites owner data
                if staged.exists():staged.unlink()
            if not target.is_file() or digest_file(target)!=operation['sha256']:
                raise ValueError('Installed file changed before commit')
            if index not in journal['completed']:
                journal['completed'].append(index);write_json(journal_path,journal)
            if after_operation:after_operation(index)
        receipt={'schema':1,'package_id':plan['package']['id'],'version':plan['package']['version'],
                 'package_digest':plan['package_digest'],'company_id':self.authority.company_id,
                 'owned_files':{row['path']:row['sha256'] for row in plan['actions'] if row['action']=='install_new_file'},
                 'reused_owner_files':[row['path'] for row in plan['actions'] if row['action']=='reuse_owner_file'],
                 'actor':actor,'production_releases_created':0,'external_effects':0}
        write_json(self.home.root/'.spielos/packages'/(expected_digest+'.json'),receipt)
        journal.update(status='complete',receipt=receipt);write_json(journal_path,journal)
        return receipt
