"""Owner-owned executable brand references and immutable content releases."""
from pathlib import Path
import hashlib,json,re,base64,html
from .home import CompanyHome,canonical,fingerprint,write_json
from .security import CompanyAuthority


class BrandRegistry:
    def __init__(self,home,principal):
        self.home=CompanyHome(home);self.authority=CompanyAuthority(home)
        self.principal=principal;self.authority.authorize(principal,'read');self.home.require_ready()
        self.root=self.home.content/'brand'

    def _file(self,name):
        if not isinstance(name,str) or not name or '\\' in name:raise ValueError('Brand reference must be a contained file name')
        relative=Path(name)
        path=self.root/relative
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix()!=name or path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()) or not path.is_file():
            raise ValueError('Brand references must be existing contained files')
        return path

    def candidate(self,*,version,files):
        self.authority.authorize(self.principal,'build')
        if not isinstance(version,str) or not version.strip():raise ValueError('Brand version is required')
        if not isinstance(files,list) or not files or len(files)>10000 or any(not isinstance(name,str) for name in files) or len(set(files))!=len(files):
            raise ValueError('Brand release needs distinct contained file references')
        files=list(files)
        contract=None
        if (self.root/'brand.json').exists():
            if 'brand.json' not in files:files.append('brand.json')
            contract=json.loads(self._file('brand.json').read_text())
            roles=contract.get('roles') if isinstance(contract,dict) else None
            if not isinstance(contract,dict) or contract.get('schema')!=1 or not isinstance(roles,dict) or set(roles)!={'voice','tokens','components','assets','templates','examples'}:
                raise ValueError('Brand contract needs versioned voice, tokens, components, assets, templates and examples roles')
            for names in roles.values():
                if not isinstance(names,list) or not names or any(not isinstance(name,str) for name in names) or len(names)!=len(set(names)):
                    raise ValueError('Each brand role needs distinct actual file references')
                if not set(names).issubset(files):raise ValueError('Brand role references must be included in the pinned files')
        else:
            # The conventional starter remains supported, without prescribing
            # a report, poster, slide, website or any particular CSS classes.
            roles={'voice':['voice.md'],'tokens':['design-system/tokens.json'],
                   'components':['design-system/components.css']}
            if not set(sum(roles.values(),[])).issubset(files):
                raise ValueError('Brand release requires voice, tokens and executable components')
            for role in ('assets','templates','examples'):
                roles[role]=[name for name in files if name.startswith(role+'/')]
                if not roles[role]:raise ValueError('Brand release needs reusable templates, real assets and example output')
        snapshot={};contents={};total=0
        for name in sorted(files):
            path=self._file(name);total+=path.stat().st_size
            if total>128*1024*1024:raise ValueError('Brand references exceed 128 megabytes')
            content=path.read_bytes()
            if not content:raise ValueError('Brand references cannot be empty')
            snapshot[name]={'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)}
            contents[name]=content
        token_names=set();css_text=[]
        for name in roles['tokens']:
            text=contents[name].decode('utf-8')
            if Path(name).suffix=='.json':
                tokens=json.loads(text)
                if not isinstance(tokens,dict) or not tokens:raise ValueError('Design tokens need a nonempty semantic map')
                # Starter token maps retain their concrete value validation.
                if 'tokens' in tokens:
                    values=tokens['tokens']
                    if tokens.get('schema')!=1 or not isinstance(values,dict) or not values or any(not re.fullmatch(r'[a-z][a-z0-9-]*',key) or not isinstance(value,str) or not value for key,value in values.items()):
                        raise ValueError('Design tokens must have valid names and concrete values')
                    token_names.update(values)
            elif Path(name).suffix=='.css':
                if not re.search(r'--[a-zA-Z][\w-]*\s*:',text):raise ValueError('CSS token references need actual custom property definitions')
                css_text.append(text)
            else:raise ValueError('Design tokens must be versioned JSON or CSS files')
        for name in roles['components']:
            if Path(name).suffix not in {'.css','.html','.svg','.js','.mjs','.jsx','.ts','.tsx'}:
                raise ValueError('Components must reference actual CSS, markup or source modules')
            text=contents[name].decode('utf-8')
            if not text.strip() or (Path(name).suffix=='.css' and not re.search(r'[^{}]+\{[^{}]+\}',text)):
                raise ValueError('Executable component references need actual implementation')
            if Path(name).suffix=='.css':css_text.append(text)
        # Validate the explicit CSS token vocabulary, including properties
        # defined by the component system itself. Framework/JSON token
        # formats are inspected by their own harness and rendered review.
        token_names.update(re.findall(r'--([a-zA-Z][\w-]*)\s*:', '\n'.join(css_text)))
        if token_names:
            unknown=set(re.findall(r'var\(\s*--([a-zA-Z][\w-]*)\s*\)', '\n'.join(css_text)))-token_names
            if unknown:raise ValueError('Components refer to undefined tokens')
        candidate={'schema':1,'company_id':self.authority.company_id,'version':version,
                'files':snapshot,'builder':self.principal.subject,'status':'candidate'}
        if contract is not None:candidate['contract']=contract
        path=self.home.root/'.spielos/artifacts/brand-candidates'/(fingerprint(candidate)+'.json')
        if not path.exists():write_json(path,candidate)
        return candidate

    def release(self,candidate,*,inspection):
        actor=self.authority.authorize(self.principal,'review')
        if candidate.get('company_id')!=self.authority.company_id:raise PermissionError('Brand belongs to another company')
        if candidate.get('builder')==actor:raise PermissionError('An independent reviewer must inspect the brand example')
        record=self.home.root/'.spielos/artifacts/brand-candidates'/(fingerprint(candidate)+'.json')
        if not record.is_file() or json.loads(record.read_text())!=candidate:
            raise ValueError('Review must refer to a recorded brand candidate')
        current=self.candidate_for_review(candidate)
        if current['files']!=candidate['files']:raise ValueError('Brand changed since the release preview')
        if not isinstance(inspection,dict) or inspection.get('candidate_digest')!=fingerprint(candidate) or not inspection.get('observations'):
            raise ValueError('Brand needs an attributable inspection of the exact candidate')
        render_name=inspection.get('render','')
        examples=candidate.get('contract',{}).get('roles',{}).get('examples',[name for name in candidate['files'] if name.startswith('examples/')])
        if render_name not in examples or render_name not in candidate['files']:raise ValueError('Rendered review must refer to a pinned brand example')
        render=self._file(render_name)
        if hashlib.sha256(render.read_bytes()).hexdigest()!=inspection.get('render_digest'):
            raise ValueError('Rendered brand evidence changed')
        if not render.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Brand inspection must reference a rendered PNG, not a source filename')
        release={**candidate,'status':'approved','reviewer':actor,'inspection':inspection,
                 'content':{name:base64.b64encode(self._file(name).read_bytes()).decode() for name in candidate['files']}}
        release_digest=fingerprint(release)
        path=self.root/'releases'/(release_digest+'.json')
        if path.exists():
            if json.loads(path.read_text())!=release:raise ValueError('Brand releases are immutable')
        else:write_json(path,release)
        return release_digest

    def candidate_for_review(self,candidate):
        # The reviewer may inspect but cannot change or add files through review.
        files={name:{'sha256':hashlib.sha256(self._file(name).read_bytes()).hexdigest(),
                     'bytes':self._file(name).stat().st_size} for name in candidate['files']}
        return {**candidate,'files':files}

    def resolve(self,release_digest):
        self.authority.authorize(self.principal,'read')
        if not re.fullmatch(r'[0-9a-f]{64}',release_digest):raise ValueError('Invalid brand release identity')
        path=self._file('releases/'+release_digest+'.json')
        release=json.loads(path.read_text())
        if fingerprint(release)!=release_digest or release.get('status')!='approved' or release.get('company_id')!=self.authority.company_id:
            raise ValueError('Brand release is not an approved immutable reference')
        for name,record in release['files'].items():
            if hashlib.sha256(base64.b64decode(release['content'][name],validate=True)).hexdigest()!=record['sha256']:
                raise ValueError('Pinned brand release content changed')
        return release


def render_report(brand_root,values):
    """Render the shipped report template with escaped business content."""
    root=Path(brand_root)
    required={'company_name','title','description','metrics','source_note'}
    if not isinstance(values,dict) or set(values)!=required or not isinstance(values['metrics'],list) or not values['metrics']:
        raise ValueError('Report needs a company label, title, description, measures and source note')
    for key in required-{'metrics'}:
        if not isinstance(values[key],str) or not values[key].strip():raise ValueError('Report text fields must be explicit')
    tokens=json.loads((root/'design-system/tokens.json').read_text())['tokens']
    substitutions={key:html.escape(value,quote=True) for key,value in values.items() if key!='metrics'}
    cards=[]
    for metric in values['metrics']:
        if not isinstance(metric,dict) or set(metric)!={'label','value'}:raise ValueError('Measures need a label and value')
        cards.append('<article class="metric-card"><h2>'+html.escape(str(metric['label']))+'</h2><span class="metric-value">'+html.escape(str(metric['value']))+'</span></article>')
    substitutions.update(tokens_css=':root {'+';'.join('--'+key+':'+value for key,value in tokens.items())+'}',
        components_css=(root/'design-system/components.css').read_text(),metric_cards=''.join(cards),
        mark_url='data:image/svg+xml;base64,'+base64.b64encode((root/'assets/example-mark.svg').read_bytes()).decode())
    template=(root/'templates/report.html').read_text()
    if set(re.findall(r'{{([a-z_]+)}}',template))-set(substitutions):raise ValueError('Template references an undefined report field')
    return re.sub(r'{{([a-z_]+)}}',lambda match:substitutions[match.group(1)],template)
