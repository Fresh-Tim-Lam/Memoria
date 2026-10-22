# -*- coding: utf-8 -*-
"""E25 / E26 证据驱动器：起 harness（真 UIAPI + 临时 KB）→ 跑 _e2526_probe.mjs → 汇总。

用法：
    python scripts/benchmark/surface/_e2526_run.py --phase after
    python scripts/benchmark/surface/_e2526_run.py --phase before   # app.js 用 HEAD 版本（修前）

--phase before 的实现：把静态资源整树复制到临时目录，只把 `app/js/app.js` 换成
`git show HEAD:...app.js`（工作区文件一个字节都不动）。后端保持当前版本（修前的前端本来
就不会调用新 RPC，所以"吞图"行为与真实修前一致）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

APP_JS_REL = "app/js/app.js"
STATIC_ROOT = REPO_ROOT / "src" / "memoria" / "ui" / "static"
LONG_DOC = "notes/long.md"


def _load_run_probe():
    import importlib.util

    spec = importlib.util.spec_from_file_location("memoria_run_probe_e2526", str(HERE / "run_probe.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _make_kb(root: Path) -> Path:
    kb = root / "kb"
    (kb / "notes").mkdir(parents=True, exist_ok=True)
    (kb / "docs").mkdir(parents=True, exist_ok=True)
    # 300 行纯文本：足够让源码面板出现滚动，且不含公式/图片（避免懒加载干扰几何测量）
    lines = ["# Long doc (E26/E25 probe)", ""]
    for i in range(1, 301):
        lines.append("line %03d — quick brown fox jumps over the lazy dog" % i)
    (kb / LONG_DOC).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (kb / "docs" / "b.md").write_text("# B\n\nsecond doc\n", encoding="utf-8")
    return kb


def _prepare_static(phase: str, root: Path, before_rev: str) -> Path | None:
    """phase=before ⇒ 返回替换过 app.js 的临时静态根；否则 None（用真实根）。"""
    if phase != "before":
        return None
    dst = root / "static-before"
    shutil.copytree(STATIC_ROOT, dst)
    old = subprocess.check_output(
        ["git", "show", "%s:src/memoria/ui/static/app/js/app.js" % before_rev], cwd=str(REPO_ROOT)
    )
    (dst / APP_JS_REL).write_bytes(old)
    if b"insertClipboardImages" in old or b"_keepCaretVisible" in old:
        raise SystemExit("before-rev %s 的 app.js 仍含 E25/E26 代码，换一个更早的 rev" % before_rev)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["before", "after"], default="after")
    ap.add_argument("--label", default="")
    # 修前基线：默认取「E26 提交」的父提交（= 未含 E25/E26 的 app.js）
    ap.add_argument("--before-rev", default="613a3936^",
                    help="phase=before 时用该 rev 的 app.js（默认 E26 提交 613a3936 的父提交）")
    args = ap.parse_args()
    label = args.label or ("e2526-" + args.phase)

    tmp = Path(tempfile.mkdtemp(prefix="memoria_e2526_%s_" % args.phase))
    kb = _make_kb(tmp)
    cfg = tmp / "cfg"
    cfg.mkdir()
    os.environ["MEMORIA_CONFIG_DIR"] = str(cfg)   # 密封配置：不继承开发机 ui-settings.json
    os.environ["MEMORIA_HARNESS_KB"] = str(kb)

    port = _free_port()
    rp = _load_run_probe()
    harness = rp.load_harness(kb, port)
    static_override = _prepare_static(args.phase, tmp, args.before_rev)
    if static_override is not None:
        harness.UI_STATIC_ROOT = static_override
        print("[e2526] 修前静态根（app.js=HEAD）: %s" % static_override)
    import bottle

    threading.Thread(
        target=bottle.run,
        kwargs=dict(app=harness.app, host="127.0.0.1", port=port, quiet=True),
        daemon=True,
    ).start()
    if not rp.wait_port(port):
        print("[e2526] harness 未起来", file=sys.stderr)
        return 2
    url = "http://127.0.0.1:%s/" % port
    for _ in range(5):
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                r.read(2048)
            break
        except Exception:
            time.sleep(0.4)
    print("[e2526] harness 就绪: %s（KB=%s）" % (url, kb))

    out = REPO_ROOT / "artifacts" / "agent" / "verify" / "e2526" / ("probe-%s.json" % args.phase)
    cmd = [
        "node", str(HERE / "_e2526_probe.mjs"),
        "--url", url, "--phase", args.phase, "--out", str(out),
        "--shotDir", str(out.parent),
    ]
    print("[e2526] 起 node: %s" % " ".join(cmd))
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=600)
    if cp.stdout:
        print(cp.stdout.strip()[:4000])
    if cp.returncode != 0 and cp.stderr:
        print("[e2526] node stderr:\n%s" % cp.stderr.strip()[:4000], file=sys.stderr)

    # ── 文件系统侧证据：.memoria/images/ 到底落了几份 ──
    img_dir = kb / ".memoria" / "images"
    files = sorted(p.name for p in img_dir.iterdir()) if img_dir.is_dir() else []
    reg = {}
    reg_path = img_dir / "registry.json"
    if reg_path.is_file():
        try:
            reg = json.loads(reg_path.read_text(encoding="utf-8"))
        except ValueError:
            reg = {}
    md = (kb / LONG_DOC).read_text(encoding="utf-8") if (kb / LONG_DOC).is_file() else ""
    refs = [ln for ln in md.split("\n") if ".memoria/images/" in ln]
    fs = {
        "phase": args.phase, "kb": str(kb), "imagesDir": str(img_dir),
        "imageFiles": files, "imageFileCount": len(files),
        "mdImageLines": refs, "mdImageLineCount": len(refs),
        "mdDistinctImagePaths": sorted({r.split("(")[-1].rstrip(")").strip("<> ") for r in refs}),
        "registryRefs": (reg or {}).get("refs") or {},
        "probeExit": cp.returncode,
    }
    fs_path = out.parent / ("fs-%s.json" % args.phase)
    fs_path.parent.mkdir(parents=True, exist_ok=True)
    fs_path.write_text(json.dumps(fs, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[e2526] FS 证据（%s）：图片文件 %d 个 %s" % (args.phase, len(files), files))
    print("[e2526] MD 图片行 %d 行，distinct %d：%s" % (len(refs), len(fs["mdDistinctImagePaths"]), fs["mdDistinctImagePaths"]))
    print("[e2526] registry refs: %s" % json.dumps(fs["registryRefs"], ensure_ascii=False)[:400])
    print("[e2526] 产物：%s / %s" % (out, fs_path))
    print("[e2526] 临时目录（保留供取证）: %s" % tmp)
    return cp.returncode


if __name__ == "__main__":
    raise SystemExit(main())
