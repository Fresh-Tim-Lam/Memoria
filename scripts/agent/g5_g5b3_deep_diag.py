"""G5b-3 深度诊断：11 个 sidecar 在 width=80 vs width=4096 下 load→save 的字节变化根因。

关键疑点：之前 width=80 时 10/11 字节不变；width=4096 后反而 4/11 不变。
要搞清：每个文件的原始字节是"已折行"还是"未折行"，以及重存后是"展开"还是"再折行"。

只读 frozen，写临时目录。用法：python scripts/agent/g5_g5b3_deep_diag.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

FROZEN = REPO / "artifacts" / "agent" / "verify" / "debate" / "kg-retrieval" / "round2" / "frozen" / "数字通信原理" / ".memoria" / "sidecars"


def _analyze(sc: Path, width: int) -> dict:
    """对单文件做 load→save(width)→二进制对比，返回诊断。"""
    import yaml

    from memoria.storage.sidecar import load_sidecar, save_sidecar

    with tempfile.TemporaryDirectory(prefix="g5-deep-") as td:
        tmp = Path(td) / "s.yaml"
        shutil.copy2(sc, tmp)
        orig_bytes = sc.read_bytes()
        data = load_sidecar(tmp)
        # 用指定 width 手动 dump 到字节（模拟 atomic_write_yaml 的 width）
        import io
        buf = io.StringIO()
        yaml.safe_dump(data, buf, allow_unicode=True, sort_keys=False, width=width)
        # atomic_write_yaml 用文本模式 open(w)，Windows 会写 CRLF；这里模拟 os.linesep
        text = buf.getvalue()
        text = text.replace("\n", "\r\n") if "\r\n" in orig_bytes.decode("utf-8", "replace") else text
        after_bytes = text.encode("utf-8")
        return {
            "orig_bytes": len(orig_bytes),
            "orig_crlf": orig_bytes.count(b"\r\n"),
            "after_bytes": len(after_bytes),
            "equal": orig_bytes == after_bytes,
            "orig_lines": orig_bytes.count(b"\n"),
            "after_lines": after_bytes.count(b"\n"),
        }


def main() -> int:
    sidecars = sorted(FROZEN.rglob("*.yaml"))
    print(f"{'文件':<40}{'原始CRLF':>8}{'原始行':>8} | {'w80相等':>8}{'w4096相等':>10}")
    print("-" * 90)
    for sc in sidecars:
        r80 = _analyze(sc, 80)
        r4096 = _analyze(sc, 4096)
        name = sc.name
        print(f"{name:<40}{r80['orig_crlf']:>8}{r80['orig_lines']:>8} | "
              f"{str(r80['equal']):>8}{str(r4096['equal']):>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
