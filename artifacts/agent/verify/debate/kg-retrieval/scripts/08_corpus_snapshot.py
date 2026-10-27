# -*- coding: utf-8 -*-
"""08_corpus_snapshot.py — pin the corpus state used by all measurements.

The studied KB is being edited live while the debate runs (file mtimes move
during the analysis window), so every measurement needs a content snapshot to
be reproducible. This writes data/corpus-snapshot.json with sha256 of every md
and every sidecar yaml under the 5 real KBs, plus the sampling timestamp.

Run: python 08_corpus_snapshot.py
"""
import os
import json
import hashlib
import datetime
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kpcore as K  # noqa: E402


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    data = K.ensure_data_dir()
    snap = {'taken_at': datetime.datetime.now().isoformat(timespec='seconds'), 'kbs': {}}
    for kb, root in K.KB_ROOTS.items():
        files = K.md_files(root)
        sidecars = K.sidecar_paths(root)
        snap['kbs'][kb] = {
            'md': [{'path': K.rel(p, root), 'sha256': sha(p), 'bytes': os.path.getsize(p)} for p in files],
            'sidecars': [{'path': K.rel(p, root), 'sha256': sha(p), 'bytes': os.path.getsize(p)} for p in sidecars],
        }
    tgt = K.TARGET_KB
    snap['target_md_hashes'] = {x['path']: x['sha256'] for x in snap['kbs'][tgt]['md']}
    with open(os.path.join(data, 'corpus-snapshot.json'), 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    n_md = sum(len(v['md']) for v in snap['kbs'].values())
    n_sc = sum(len(v['sidecars']) for v in snap['kbs'].values())
    print(f"# corpus snapshot {snap['taken_at']}: {n_md} md, {n_sc} sidecars across {len(K.KB_ROOTS)} KBs")
    for kb, v in snap['kbs'].items():
        print(f"- {kb}: {len(v['md'])} md, {len(v['sidecars'])} sidecars")
    print('wrote data/corpus-snapshot.json')


if __name__ == '__main__':
    main()
