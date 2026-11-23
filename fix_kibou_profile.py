#!/usr/bin/env python3
"""Merge KibouAkari profile widgets into one terminal and harden GitHub fetch.
Run from the root of the KibouAkari/KibouAkari checkout.
"""
from pathlib import Path
import ast
import shutil
import sys
from datetime import datetime, timezone

root = Path.cwd()
generator = root / 'scripts/generate.py'
readme = root / 'README.md'
workflow = root / '.github/workflows/update-profile.yml'
for path in [generator, readme, workflow, root / 'scripts/portrait.json']:
    if not path.is_file():
        sys.exit(f'Not the expected KibouAkari profile checkout, missing: {path}')

src = generator.read_text(encoding='utf-8')
md = readme.read_text(encoding='utf-8')
yml = workflow.read_text(encoding='utf-8')
if 'def build_combined(d):' in src:
    sys.exit('Already patched. No changes made.')

def replace_once(value, old, new, context):
    if value.count(old) != 1:
        sys.exit(f'Expected exactly one occurrence of {context}, found {value.count(old)}. Nothing changed.')
    return value.replace(old, new, 1)

src = replace_once(src,
    'import json, os, sys, datetime as dt, urllib.request, random',
    'import json, os, sys, datetime as dt, urllib.request, urllib.error, random, time\nimport xml.etree.ElementTree as ET',
    'generator imports')
src = replace_once(src,
    '    req = urllib.request.Request(\n        "https://api.github.com/graphql",',
    '    token = os.environ.get("GH_TOKEN")\n'
    '    if not token:\n'
    '        raise RuntimeError("GH_TOKEN missing; configure METRICS_TOKEN or use GITHUB_TOKEN fallback")\n'
    '    req = urllib.request.Request(\n        "https://api.github.com/graphql",',
    'GraphQL request')
src = replace_once(src, 'os.environ[\'GH_TOKEN\']', 'token', 'token expression')
src = replace_once(src,
    '    with urllib.request.urlopen(req, timeout=60) as r:\n        data = json.load(r)',
    '    for attempt in range(3):\n'
    '        try:\n'
    '            with urllib.request.urlopen(req, timeout=60) as r:\n'
    '                data = json.load(r)\n'
    '            break\n'
    '        except urllib.error.HTTPError as exc:\n'
    '            detail = exc.read(1200).decode("utf-8", "replace")\n'
    '            if exc.code in (429, 500, 502, 503, 504) and attempt < 2:\n'
    '                time.sleep(3 * (2 ** attempt))\n'
    '                continue\n'
    '            raise RuntimeError(f"GitHub GraphQL HTTP {exc.code}: {detail}") from exc',
    'GraphQL response')
combined = '''def build_combined(d):
    """One continuous shell session, with no secondary frame or divider."""
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    terminal = ET.fromstring(build_terminal(d))
    activity_xml = build_activity(d).replace('id="t', 'id="activity-t').replace(
        'url(#t', 'url(#activity-t')
    activity = ET.fromstring(activity_xml)

    W, H = 940, 1040
    s = Svg(W, H)
    s.frame("kibouakari@mainframe: ~", "bash")

    # Root children: title, defs, five frame components, actual SVG content.
    for part in (terminal, activity):
        defs = list(part)[1]
        s.defs.extend(ET.tostring(node, encoding="unicode") for node in defs)

    terminal_nodes = list(terminal)[7:]
    # Drop the old idle prompt/cursor; we add exactly one at the very bottom.
    terminal_nodes = terminal_nodes[:-2]
    terminal_markup = "".join(ET.tostring(node, encoding="unicode")
                              for node in terminal_nodes)
    activity_markup = "".join(ET.tostring(node, encoding="unicode")
                              for node in list(activity)[7:])

    # The activity commands continue where fastfetch finishes, as one shell.
    s.body.append(terminal_markup)
    s.body.append(f'<g transform="translate(0 470)">{activity_markup}</g>')
    s.body.append(prompt(20, H - 16, ""))
    s.body.append(s.cursor(36, H - 16, 0))
    return s.render("Kibou Akari: fastfetch and live GitHub activity, one terminal")

'''
src = replace_once(src, 'if __name__ == "__main__":', combined + 'if __name__ == "__main__":', 'main guard')
src = replace_once(src,
    '    (OUT / "terminal.svg").write_text(build_terminal(data), encoding="utf-8")\n'
    '    (OUT / "activity.svg").write_text(build_activity(data), encoding="utf-8")',
    '    (OUT / "terminal.svg").write_text(build_combined(data), encoding="utf-8")',
    'asset generation')
md = replace_once(md,
    '<!-- Live Activity Widget -->\n<img src="./assets/activity.svg?raw=true" alt="GitHub Activity Stats" width="100%">\n\n<br/><br/>\n\n',
    '', 'activity embed in README')
md = replace_once(md,
    '<!-- Terminal / Fastfetch Widget -->',
    '<!-- Combined fastfetch + live activity in one terminal -->',
    'terminal comment')
yml = replace_once(yml,
    'GH_TOKEN: ${{ secrets.METRICS_TOKEN }}',
    'GH_TOKEN: ${{ secrets.METRICS_TOKEN || github.token }}',
    'token workflow expression')
# Check all transformations before changing any repository file.
ast.parse(src, filename=str(generator))

stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
backup = root / f'.profile-fix-backup-{stamp}'
backup.mkdir()
for path, content in [(generator, src), (readme, md), (workflow, yml)]:
    shutil.copy2(path, backup / path.name)
    path.write_text(content, encoding='utf-8')

print(f'Updated generator, README and workflow. Backups: {backup}')
print('Run these commands next:')
print('  PREVIEW=1 python3 scripts/generate.py')
print('  python3 -m py_compile scripts/generate.py')
print('  git diff --check && git diff --stat')
print('  git add README.md scripts/generate.py .github/workflows/update-profile.yml')
print('  git commit -m "Merge profile widgets and harden metrics fetch"')
print('  git push')
print('Then use Actions > Update Profile SVGs > Run workflow to generate the live SVG.')
