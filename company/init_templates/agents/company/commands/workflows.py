"""Read declarative workflow packages without executing submitted code."""
from pathlib import Path
import hashlib,json
from ..home import CompanyHome


def read_package(home,path):
    company=CompanyHome(home)
    company.require_ready()
    path=Path(path).expanduser().resolve()
    if not path.is_relative_to(company.content/'workflows') or path.name!='workflow.json':
        raise ValueError('Choose company/workflows/<workflow>/workflow.json')
    manifest=json.loads(path.read_text())
    if path.parent.name!=manifest.get('id'):raise ValueError('Workflow folder and declaration identity differ')
    definition_sources={'workflow.json':hashlib.sha256(path.read_bytes()).hexdigest()}
    evaluation=manifest.get('evaluation',{})
    if set(evaluation)=={'rubric','cases'}:
        def contained(relative):
            name=Path(relative);target=path.parent/name
            if name.is_absolute() or '..' in name.parts or target.is_symlink() or not target.resolve().is_relative_to(path.parent):
                raise ValueError('Workflow definition escapes its package')
            return target
        rubric_path=contained(evaluation['rubric'])
        rubric=json.loads(rubric_path.read_text())
        definition_sources[rubric_path.relative_to(path.parent).as_posix()]=hashlib.sha256(rubric_path.read_bytes()).hexdigest()
        cases=[]
        for case_path in sorted(contained(evaluation['cases']).glob('*.json')):
            case_path=contained(case_path.relative_to(path.parent))
            cases.append(json.loads(case_path.read_text()))
            definition_sources[case_path.relative_to(path.parent).as_posix()]=hashlib.sha256(case_path.read_bytes()).hexdigest()
        manifest['evaluation']={**rubric,'cases':cases}
    manifest['definition_sources']=definition_sources
    brief=path.parent/'brief.md'
    if not brief.is_file() or brief.is_symlink():raise ValueError('Workflow package needs its acceptance brief')
    manifest['brief']=brief.read_text()
    manifest['definition_sources']['brief.md']=hashlib.sha256(brief.read_bytes()).hexdigest()
    return manifest
