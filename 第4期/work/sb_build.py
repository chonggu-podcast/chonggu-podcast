"""Assemble chapter storyboard files sb/ch_XX.py into one storyboard JSON.
python3 sb_build.py out.json [01 02 ...]   (no chapter list = all chapters 01..14)"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ns = {'__file__': str(HERE / 'sb_head.py')}
exec(open(HERE / 'sb_head.py').read(), ns)
import os
# PART=A / B (2026-10-05): 4.1 顾东政 = chapters 01–07, 4.2 吴原同 = chapters 08–14, with the 4.1 / 4.2 title and end card
PART = os.environ.get('PART', '')
chs = sys.argv[2:] or {'A': [f'{i:02d}' for i in range(1, 8)], 'B': [f'{i:02d}' for i in range(8, 15)]}.get(PART, [f'{i:02d}' for i in range(1, 15)])
for c in chs:
    f = HERE / 'sb' / f'ch_{c}.py'
    if not f.exists():
        print('missing', f); continue
    n0 = len(ns['S'])
    exec(compile(open(f).read(), str(f), 'exec'), ns)
    for sc in ns['S'][n0:]:
        sc.setdefault('ch', c)
sb = {'episode': 4, 'label': None, 'handoff': 'intro', 'intro_speakers': ['gu'] * 4, 'date': '2026.10.04',
      'title': {'kicker': '重估 · 第 4 期', 'head': '重估学历', 'sub': '', 'ruleW': 480},
      'end': {'kicker': '', 'head': '谢谢收听', 'foot': '重估 · 第 4 期　　2026.10.04 录制', 'ruleW': 364, 'y0': 520},
      'chapters': [], 'scenes': ns['S']}
if PART:
    for sc in sb['scenes']:   # ch 07's last scene ends where 吴原同 takes over in the joint edit; alone it runs to the end card
        if '刚刚顾老师' in str(sc.get('t1') or ''):
            sc['t1'] = None
    n = {'A': '4.1', 'B': '4.2'}[PART]
    sb['label'] = n
    sb['title'] = {'kicker': f'重估 · {n}', 'head': '重估学历', 'sub': '', 'ruleW': 480}
    sb['end']['foot'] = {'A': '重估 · 4.1\u3000\u3000下集 4.2：吴原同谈对学历祛魅',
                         'B': '重估 · 4.2\u3000\u3000上集 4.1：顾东政谈学历给他的机会'}[PART]
json.dump(sb, open(sys.argv[1], 'w'), ensure_ascii=False, indent=1)
print(len(ns['S']), 'scenes from', ' '.join(chs))
