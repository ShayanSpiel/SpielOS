"""Company-scoped local authentication and signed, expiring principals.

The filesystem owner is the local trust root. This is not remote SSO or an
enterprise identity provider. Bearer credentials are provisioned only by an
explicit owner command, stored as hashes and scoped to one company.
"""
from __future__ import annotations
from dataclasses import dataclass,field
from contextlib import contextmanager
import hashlib,hmac,json,os,secrets,time
from pathlib import Path
from .home import CompanyHome,canonical,write_json
from .platform import user_id,is_private,protect_private,is_link,locked_file

ROLE_ACTIONS={
 'owner':{'configure','build','run','evaluate','review','approve','read','export','memory'},
 'builder':{'build','evaluate','read'},
 'operator':{'run','evaluate','read','memory'},
 'reviewer':{'evaluate','review','read'},
 'approver':{'approve','read'},
 'viewer':{'read'},
}

@dataclass(frozen=True)
class Principal:
    subject:str
    company_id:str
    roles:tuple[str,...]
    expires_at:int
    proof:str=field(repr=False)
    credential_id:str=field(default="",repr=False)


class CompanyAuthority:
    def __init__(self,home):
        self.home=CompanyHome(home)
        if not self.home.lean:raise ValueError('Select an initialized lean company home')
        self.company_id=json.loads(self.home.layout_path.read_text())['company_id']
        self.root=self.home.root/'.spielos/security'
        self.key_path=self.root/'authority.key'
        self.policy_path=self.root/'principals.json'

    def bootstrap(self):
        self.home.require_destination()
        if self.root.is_symlink() or not self.root.parent.resolve().is_relative_to(self.home.root):
            raise PermissionError('Authentication directory must remain inside this company')
        created=not self.root.exists()
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if created:protect_private(self.root)
        if not is_private(self.root):
            raise PermissionError('Authentication directory must be private and owner controlled')
        if not self.key_path.exists():
            descriptor=os.open(self.key_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(descriptor,'w') as stream:stream.write(secrets.token_hex(32))
            protect_private(self.key_path)
        if not self.policy_path.exists():
            write_json(self.policy_path,{'schema':1,'company_id':self.company_id,
                'owner_uid':user_id(),'bearer_principals':{}})
            protect_private(self.policy_path)

    @contextmanager
    def _lock(self):
        self._key()
        path=self.root/'policy.lock'
        with locked_file(path):
            yield

    def _key(self):
        if not is_private(self.root):
            raise PermissionError('Company authentication directory is not private')
        if is_link(self.key_path) or is_link(self.policy_path):
            raise PermissionError('Authentication files cannot be symbolic links')
        if not self.key_path.is_file() or not self.policy_path.is_file():
            raise PermissionError('Company authentication is not configured')
        for path in (self.key_path,self.policy_path):
            if not is_private(path):
                raise PermissionError('Company authentication requires private owner-controlled files')
        return self.key_path.read_bytes()

    def _policy(self):
        self._key()
        policy=json.loads(self.policy_path.read_text())
        if policy.get('company_id')!=self.company_id:raise PermissionError('Wrong company authority')
        return policy

    def _principal(self,subject,roles,expires_at,credential_id=""):
        fields={'subject':subject,'company_id':self.company_id,'roles':sorted(roles),'expires_at':expires_at,'credential_id':credential_id}
        proof=hmac.new(self._key(),canonical(fields).encode(),hashlib.sha256).hexdigest()
        return Principal(subject,self.company_id,tuple(sorted(roles)),expires_at,proof,credential_id)

    def local_owner(self):
        policy=self._policy()
        if policy['owner_uid']!=user_id():raise PermissionError('The current OS user does not own this company')
        return self._principal(f'os:{user_id()}',('owner',),int(time.time())+3600)

    def authorize(self,principal,action):
        if not isinstance(principal,Principal) or principal.company_id!=self.company_id:
            raise PermissionError('An authenticated principal for this company is required')
        expected=self._principal(principal.subject,principal.roles,principal.expires_at,principal.credential_id)
        if not hmac.compare_digest(expected.proof,principal.proof) or principal.expires_at<=time.time():
            raise PermissionError('Authentication is invalid or expired')
        policy=self._policy()
        if principal.subject.startswith('os:'):
            if principal.subject!=f'os:{policy["owner_uid"]}' or policy['owner_uid']!=user_id():
                raise PermissionError('The owner identity no longer applies')
        else:
            record=policy['bearer_principals'].get(principal.subject,{})
            if (record.get('status')!='active' or record.get('expires_at',0)<=time.time()
                    or tuple(record.get('roles',()))!=principal.roles
                    or record.get('token_sha256')!=principal.credential_id):
                raise PermissionError('Principal was revoked or its roles changed')
        if action not in set().union(*(ROLE_ACTIONS.get(role,set()) for role in principal.roles)):
            raise PermissionError(f'Principal is not permitted to {action}')
        return principal.subject

    def issue(self,owner,*,subject,roles,lifetime_seconds=3600):
        self.authorize(owner,'configure')
        if not isinstance(subject,str) or not subject.strip() or subject.startswith('os:'):
            raise ValueError('A nonempty named service or person is required')
        if not roles or set(roles)-set(ROLE_ACTIONS) or 'owner' in roles:
            raise ValueError('Assign explicit non-owner roles')
        if not 1<=lifetime_seconds<=86400*30:raise ValueError('Credential lifetime must be bounded')
        with self._lock():
            policy=self._policy()
            if subject in policy['bearer_principals'] and policy['bearer_principals'][subject]['status']=='active':
                raise ValueError('Principal already exists; revoke it explicitly before replacing it')
            token=secrets.token_urlsafe(32)
            policy['bearer_principals'][subject]={'roles':sorted(set(roles)),
                'token_sha256':hashlib.sha256(token.encode()).hexdigest(),
                'expires_at':int(time.time())+lifetime_seconds,'status':'active'}
            write_json(self.policy_path,policy)
        return token

    def authenticate(self,token):
        if not isinstance(token,str) or not token:raise PermissionError('Bearer credential required')
        candidate=hashlib.sha256(token.encode()).hexdigest()
        for subject,record in self._policy()['bearer_principals'].items():
            if (hmac.compare_digest(record['token_sha256'],candidate) and record['status']=='active'
                    and record['expires_at']>time.time()):
                return self._principal(subject,record['roles'],record['expires_at'],record['token_sha256'])
        raise PermissionError('Bearer credential is invalid, revoked or expired')

    def revoke(self,owner,subject):
        self.authorize(owner,'configure')
        with self._lock():
            policy=self._policy()
            if subject not in policy['bearer_principals']:raise KeyError('Unknown principal')
            policy['bearer_principals'][subject]['status']='revoked'
            write_json(self.policy_path,policy)
