#!/usr/bin/env python3
"""G5.2 出口门禁断言：validate 0-issue / repair 干跑与实操一致 / diagnose-images 结构化输出。

用法：python scripts/benchmark/maintenance/cli_assert_g5_2.py
退出码 0=全 PASS，1=有 FAIL。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "benchmark" / "maintenance"))

import gen_maintenance_kb as gen  # noqa: E402
from memoria.storage.manifest import build_manifest_entries, save_manifest  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, extra=None) -> None:
    print(("PASS  " if cond else "FAIL  ") + name + (f"  {extra}" if extra is not None else ""))
    if not cond:
        fails.append(name)


def cli(*args: str):
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    p = subprocess.run(
        [sys.executable, "-m", "memoria.cli.main", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    return p.returncode, p.stdout, p.stderr


# 图片引用夹具：正常 / 不可注册（裸 URL 含空格→会被截断）/ 文件缺失
DIAG_MD = """## KP 诊断样例

正常引用（图片存在）：

![](<.memoria/images/dot.png>)

不可注册（裸 URL 含空格，会被截断）：

![]( .memoria/images/my file.png )

文件缺失（格式可注册但图片不存在）：

![](<.memoria/images/ghost.png>)
"""


def snapshot(kb: Path) -> dict:
    out = {}
    for p in sorted(kb.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[str(p.relative_to(kb)).replace("\\", "/")] = (st.st_size, st.st_mtime_ns)
    return out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="g52_"))
    kb = tmp / "kb"
    try:
        gen.gen(str(kb), files=6, seed=20260910, images=True)
        # 诊断夹具文档；新增后重建 manifest 基线，避免把"未登记文件"混入 validate
        (kb / "diag_images.md").write_text(DIAG_MD, encoding="utf-8")
        save_manifest(str(kb), build_manifest_entries(str(kb)))

        # 1) validate：受控语料应 0 error
        code, out, err = cli("validate", str(kb), "--json")
        rep = json.loads(out)
        check("validate status=ok", rep.get("status") == "ok", rep.get("status"))
        check("validate errors=0", rep.get("errors") == 0, rep.get("errors"))

        # 2) diagnose-images：结构化输出 + 分类正确
        code, out, err = cli("diagnose-images", str(kb), "--json")
        diag = json.loads(out)
        unreg = diag.get("unregistered") or []
        missing = diag.get("missing") or []
        check("diagnose status=ok", diag.get("status") == "ok", diag.get("status"))
        check("diagnose unregistered=1", len(unreg) == 1, len(unreg))
        check("diagnose missing=1", len(missing) == 1, len(missing))
        check(
            "diagnose 条目字段合法",
            all(
                {"doc", "line", "src", "url", "exists"} <= set(it)
                and isinstance(it["line"], int)
                and it["line"] > 0
                for it in unreg + missing
            ),
        )
        check("diagnose missing.exists 全 False", all(it["exists"] is False for it in missing))
        check("diagnose 退出码=1（存在待处理项）", code == 1, code)

        # 3) repair：干跑不写盘 + 与 apply 的 move 集合一致
        os.replace(kb / "d1/f_00001.md", kb / "d1/renamed_00001.md")
        before = snapshot(kb)

        code, out, err = cli("repair-paths", str(kb), "--json")
        dry = json.loads(out)
        after = snapshot(kb)
        dry_moves = dry.get("moves") or []
        check("dry-run 检出移动=1", len(dry_moves) == 1, dry_moves)
        check("dry-run dry_run=True", bool(dry.get("dry_run")), dry.get("dry_run"))
        check("dry-run 未写盘（文件快照一致）", before == after)
        dry_pairs = {(m.get("from"), m.get("to")) for m in dry_moves}

        code, out, err = cli("repair-paths", str(kb), "--apply", "--json")
        app = json.loads(out)
        app_pairs = {(m.get("from"), m.get("to")) for m in (app.get("applied") or [])}
        check(
            "apply 计数一致（applied=move=1）",
            app.get("applied_count") == app.get("move_count") == 1,
            {"applied": app.get("applied_count"), "move": app.get("move_count")},
        )
        check("apply 与干跑 move 集合一致", app_pairs == dry_pairs, {"dry": dry_pairs, "apply": app_pairs})

        # 4) 修复后路径漂移消失
        code, out, err = cli("validate", str(kb), "--json")
        rep2 = json.loads(out)
        check("修复后 errors=0", rep2.get("errors") == 0, rep2.get("errors"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nG5.2 CLI 断言：{'全 PASS' if not fails else str(len(fails)) + ' 项失败'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
