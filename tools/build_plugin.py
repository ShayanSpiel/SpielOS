#!/usr/bin/env python3
"""Build a standalone desktop plugin from reusable source, outside this checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TEMPLATE=ROOT/'company/init_templates/integrations/spielos'


def files(tree):
    return [p for p in sorted(tree.rglob('*')) if p.is_file() and not p.is_symlink()
            and '__pycache__' not in p.parts and p.suffix!='.pyc']


def build(destination):
    output=Path(destination).expanduser().resolve()
    if output.is_relative_to(ROOT):raise ValueError('Build the plugin outside product source')
    if output.exists():raise ValueError('Choose a new build directory; existing files are preserved')
    output.mkdir(parents=True)
    package=output/'spielos';package.mkdir()
    for p in files(TEMPLATE):
        relative=p.relative_to(TEMPLATE);target=package/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    source=ROOT/'company'
    for p in files(source):
        relative=p.relative_to(source)
        if relative.parts[0] in {'tests','init_templates'}:continue
        target=package/'runtime/company'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    templates=source/'init_templates'
    for p in files(templates):
        relative=p.relative_to(templates)
        if relative.parts[:2]==('integrations','spielos'):continue
        target=package/'runtime/company/init_templates'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    shutil.copyfile(ROOT/'LICENSE',package/'LICENSE')
    (package/'.spielos-boundary.json').write_text('{"role":"source"}\n')
    inventory={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files(package)}
    (output/'inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
    archive=output/'spielos-desktop.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files(package):z.write(p,'spielos/'+p.relative_to(package).as_posix())
    return {'package':str(package),'archive':str(archive),'files':len(inventory)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True)
    print(json.dumps(build(parser.parse_args().out)))
