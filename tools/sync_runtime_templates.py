#!/usr/bin/env python3
"""Generate/check shipped runtime twins from reusable source; never prune."""
from pathlib import Path
import argparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'company'
TARGET = SOURCE / 'init_templates/agents/company'
SKIP = {'tests','init_templates','__pycache__'}


def sync(write=False):
    changed=[]
    for path in sorted(SOURCE.rglob('*')):
        relative=path.relative_to(SOURCE)
        if not path.is_file() or set(relative.parts)&SKIP or path.suffix=='.pyc':
            continue
        target=TARGET/relative
        if not target.is_file() or path.read_bytes()!=target.read_bytes():
            changed.append(relative.as_posix())
            if write:
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes(path.read_bytes())
    # Report removed-source leftovers too. Never delete them implicitly.
    for target in sorted(TARGET.rglob('*')):
        relative=target.relative_to(TARGET)
        if target.is_file() and not set(relative.parts)&SKIP and target.suffix!='.pyc' and not (SOURCE/relative).is_file():
            changed.append('orphan: '+relative.as_posix())
    return changed


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    differences=sync(args.write)
    print(('Generated' if args.write else 'Diverged')+f' runtime files: {len(differences)}')
    for path in differences: print(path)
    raise SystemExit(0 if not differences or (args.write and not any(p.startswith('orphan: ') for p in differences)) else 1)
