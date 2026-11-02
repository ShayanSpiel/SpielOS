#!/usr/bin/env python3
"""Export the canonical runtime as a public Codex marketplace outside source."""
import argparse
import json
from pathlib import Path
import shutil

from build_plugin import ROOT, build


def export(destination):
    result = build(destination)
    output = Path(result['package']).parent
    marketplace = output / '.agents/plugins/marketplace.json'
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(json.dumps({
        'name': 'spielos',
        'owner': {'name': 'Shayan Spiel'},
        'interface': {'displayName': 'SpielOS'},
        'plugins': [{'name': 'spielos', 'category': 'Business & Operations', 'source': {'source': 'local', 'path': './spielos'},
                     'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_USE'}}],
    }, indent=2) + '\n')
    claude = output / '.claude-plugin/marketplace.json'
    claude.parent.mkdir(parents=True)
    claude.write_text(json.dumps({'name':'spielos','owner':{'name':'Shayan Spiel'},
        'metadata':{'description':'The official SpielOS company workspace and workflow plugin.'},
        'plugins':[{'name':'spielos','source':'./spielos',
                    'description':'Lasting company context, Director, dashboard and tested workflows.'}]},indent=2)+'\n')
    shutil.copyfile(ROOT / 'README.md', output / 'README.md')
    shutil.copyfile(ROOT / 'LICENSE', output / 'LICENSE')
    for relative in ('docs/images/spielos-in-codex.png', 'docs/plugin-privacy.md', 'docs/plugin-terms.md', 'docs/tester-guide.md'):
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    # Distribution links point to the reviewed product source rather than missing files.
    readme = output / 'README.md'
    text = readme.read_text()
    for relative in ('company/README.md', 'company/ARCHITECTURE.md', 'company/EVALUATION.md',
                     'docs/reviews/2026-11-02-technical-review.md', 'docs/reviews/2026-11-02-ci-repair.md'):
        text = text.replace('](' + relative + ')', '](https://github.com/ShayanSpiel/SpielOS/blob/main/' + relative + ')')
    text += '\n## Updates and provenance\n\nThis is the generated desktop distribution of [SpielOS](https://github.com/ShayanSpiel/SpielOS), not a separate implementation. Ask Codex to refresh the SpielOS marketplace and update the plugin. Existing company folders are preserved; apply company-template updates explicitly from the selected company. Maintainers export each reviewed source release with `tools/export_plugin_marketplace.py --out <new directory>` and publish the generated inventory and package together.\n'
    readme.write_text(text)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True)
    print(json.dumps(export(parser.parse_args().out)))
