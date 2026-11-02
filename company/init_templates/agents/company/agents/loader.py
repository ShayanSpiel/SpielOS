"""Load installed Agent declarations from the canonical user layer.

``agents/installed/*.json`` is one of the six preserved owner layers: each
file declares one replaceable Agent (id, skills, permissions, produces,
connections). This module makes those declarations visible to the runtime —
``CleanCommandRuntime`` passes them as the ``agents=`` dict of
``GoalRuntime``/``ResolutionCycle`` — so workflow steps resolve to their
declared identity instead of a bare ``Agent(agent_id)``. Loading is
best-effort per file: an unparseable declaration is skipped, never fatal.
"""

from __future__ import annotations

import json
from pathlib import Path

from .core import Agent

#: Keys of an installed declaration that map onto the Agent record.
_TUPLE_KEYS = ("skill_ids", "capability_ids", "permissions", "produces",
               "connection_ids")


def _candidate_roots(project_root: Path | None) -> list[Path]:
    """Installed layers to probe, most specific first."""
    from ..runtime.paths import find_project_root

    roots: list[Path] = []
    if project_root is not None:
        home = Path(project_root)
        from ..home import CompanyHome
        if CompanyHome(home).lean:
            return [CompanyHome(home).content / "agents" / "installed"]
        roots.append(home / ".agents" / "company" / "agents" / "installed")
    root = Path(project_root) if project_root is not None else find_project_root()
    roots.append(root / ".agents" / "company" / "agents" / "installed")
    # A flat source checkout has no .agents tree; its installed layer is
    # the agents package's own installed/ folder — <repo>/company/agents/
    # installed (parents[1] is the company package), anchored on this file
    # so the probe lands beside the loader, never in a sibling of it.
    roots.append(Path(__file__).resolve().parents[1] / "agents" / "installed")
    seen, unique = set(), []
    for item in roots:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def installed_agents_root(project_root: Path | None = None) -> Path:
    """The installed Agent layer for one home (first that exists)."""
    for candidate in _candidate_roots(project_root):
        if candidate.is_dir():
            return candidate
    return _candidate_roots(project_root)[0]


def _declaration_to_agent(data: dict) -> Agent | None:
    agent_id = data.get("id")
    if not isinstance(agent_id, str) or not agent_id:
        return None
    values: dict[str, object] = {}
    description = data.get("description")
    if isinstance(description, str):
        values["description"] = description
    for key in _TUPLE_KEYS:
        raw = data.get(key)
        if isinstance(raw, str):
            raw = (raw,)
        if raw is not None:
            if not isinstance(raw,(list,tuple)) or any(not isinstance(item,str) for item in raw):return None
            values[key] = tuple(raw)
    return Agent(agent_id, **values)


def available_agents(project_root: Path | None = None) -> dict[str, Agent]:
    """Every installed Agent declaration keyed by id (empty is fine)."""
    root = installed_agents_root(project_root)
    agents: dict[str, Agent] = {}
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # a broken declaration never blocks the runtime
        if not isinstance(data, dict):
            continue
        agent = _declaration_to_agent(data)
        if agent is not None:
            agents[agent.id] = agent
    return agents


__all__ = ["available_agents", "installed_agents_root"]


def validate_declaration(data, *, content):
    """Fail closed for creation; return the resolved, non-secret declaration."""
    import re
    if not isinstance(data,dict) or not re.fullmatch(r'[a-z][a-z0-9-]{0,62}',str(data.get('id',''))):
        raise ValueError('Agent needs a lowercase portable identity')
    if not isinstance(data.get('description'),str) or not data['description'].strip():
        raise ValueError('Agent needs a concrete responsibility')
    for key in _TUPLE_KEYS:
        raw=data.get(key,[])
        if not isinstance(raw,list) or any(not isinstance(item,str) or not item.strip() for item in raw) or len(raw)!=len(set(raw)):
            raise ValueError('Agent '+key+' must be a list of distinct names')
    if set(data.get('permissions',[]))-{'read_company','write_artifacts'}:
        raise ValueError('Draft agents may read scoped context and write artifacts; external effects need exact-action approval')
    content=Path(content).resolve()
    for skill in data.get('skill_ids',[]):
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}',skill):raise ValueError('Invalid skill identity')
        path=content/'skills'/skill/'SKILL.md'
        if not path.is_file() or not path.resolve().is_relative_to(content):raise ValueError('Agent references a missing or external skill')
    for connection in data.get('connection_ids',[]):
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}',connection):raise ValueError('Invalid connection identity')
        path=content/'connections'/(connection+'.json')
        if not path.is_file() or path.is_symlink():raise ValueError('Agent references a missing connection declaration')
        declaration=json.loads(path.read_text())
        if not isinstance(declaration,dict) or set(declaration)-{'id','provider','credential_ref','permissions'} or not declaration.get('credential_ref'):
            raise ValueError('Connection declarations contain references and permissions, never credentials')
    return {**data,**{key:list(data.get(key,[])) for key in _TUPLE_KEYS}}


class AgentCatalog:
    """One company's reusable declarations; creating one never starts it."""
    def __init__(self,home,principal):
        from ..home import CompanyHome
        from ..security import CompanyAuthority
        self.home=CompanyHome(home);self.authority=CompanyAuthority(home)
        self.principal=principal;self.authority.authorize(principal,'read')
        self.home.require_ready()

    def create_skill(self,*,name,description,instructions):
        import re
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}',name) or len(name)>63:raise ValueError('Skill name is not portable')
        if not isinstance(description,str) or not description.strip() or '\n' in description:raise ValueError('Skill needs a one-line discovery description')
        if not isinstance(instructions,str) or not instructions.strip():raise ValueError('Skill needs actionable task instructions')
        self.authority.authorize(self.principal,'build')
        path=self.home.content/'skills'/name/'SKILL.md'
        if path.parent.exists():raise FileExistsError('Skill already exists; review a versioned change explicitly')
        path.parent.mkdir(parents=True)
        path.write_text('---\nname: '+name+'\ndescription: '+json.dumps(description)+'\n---\n\n'+instructions.strip()+'\n')
        return path

    def create_agent(self,data):
        from ..home import write_json
        self.authority.authorize(self.principal,'build')
        declaration=validate_declaration(data,content=self.home.content)
        path=self.home.content/'agents/installed'/(declaration['id']+'.json')
        if path.exists():raise FileExistsError('Agent already exists; review a versioned change explicitly')
        write_json(path,declaration)
        config=self.home.root/'.spielos/telemetry.json'
        if config.is_file() and json.loads(config.read_text()).get('automatic',{}).get('enabled'):
            from ..workflows.runs import WorkflowRuntime
            from ..observability.evaluators import register_agent
            runtime=WorkflowRuntime(self.home.root/'.spielos/state/workflows.sqlite',home=self.home.root,principal=self.principal)
            register_agent(runtime,declaration)
        return path

    def resolve(self,identity):
        import re,hashlib
        self.authority.authorize(self.principal,'read')
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,62}',identity):raise ValueError('Invalid agent identity')
        path=self.home.content/'agents/installed'/(identity+'.json')
        if not path.is_file() or path.is_symlink():raise ValueError('Reusable agent declaration is missing')
        declaration=validate_declaration(json.loads(path.read_text()),content=self.home.content)
        references={'agents/installed/'+identity+'.json':hashlib.sha256(path.read_bytes()).hexdigest()}
        for skill in declaration['skill_ids']:
            name='skills/'+skill+'/SKILL.md'
            references[name]=hashlib.sha256((self.home.content/name).read_bytes()).hexdigest()
        contract=self.home.content/'evaluation-and-learning-contract.md'
        if contract.is_file() and not contract.is_symlink():references['evaluation-and-learning-contract.md']=hashlib.sha256(contract.read_bytes()).hexdigest()
        return declaration,references
