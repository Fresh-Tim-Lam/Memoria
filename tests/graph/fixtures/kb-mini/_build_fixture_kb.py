"""生成 B6 用最小 KB fixture（只读事实源 + 2 条 semantic overlay）。

产物（全部为**冻结 fixture**，构建后不应被测试修改）::

    tests/graph/fixtures/kb-mini/
      docs/ch01-sampling.md
      docs/ch02-quantization.md
      notes/review.md
      .memoria/manifest.yaml
      .memoria/sidecars/docs/ch01-sampling.memoria.yaml
      .memoria/sidecars/docs/ch02-quantization.memoria.yaml
      .memoria/sidecars/notes/review.memoria.yaml

为什么需要 fixture KB：B6 的 S7 工具 / S9 检索 / GATE-RET 需要**确定性、可提交**的
KB（真实用户库会被编辑 ⇒ edition 漂移；docs/example 也会被用户改）。本 fixture 只包
含 3 篇 md + 4 个 KP + 2 条合法 semantic overlay（供 graph/hybrid/sem_purity 用）。

复跑：``python tests/graph/fixtures/kb-mini/_build_fixture_kb.py``
"""

from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KB = ROOT


def _write(rel: str, text: str) -> None:
    path = KB / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)


def _quote(file_rel: str, start: int, end: int) -> str:
    lines = io.open(KB / file_rel, encoding="utf-8").read().splitlines()
    slice_text = "\n".join(lines[start - 1:end])
    return hashlib.sha256(slice_text.encode("utf-8")).hexdigest()


CH01 = """# 第1章 抽样定理

## 1.1 低通抽样定理

低通抽样定理：对最高频率为 fmax 的低通信号，抽样频率 fs 必须不小于 2 fmax，才能无失真恢复。

## 1.2 带通抽样定理

带通抽样定理：对带宽为 B 的带通信号，抽样频率 fs 必须不小于 2B，才能无失真恢复。
"""

CH02 = """# 第2章 量化

## 2.1 均匀量化

均匀量化：量化间隔 Δ 处处相等，量化误差均匀分布。

## 2.2 非均匀量化

非均匀量化：对小信号采用小量化间隔，对大信号采用大量化间隔，以改善小信号信噪比。
"""

NOTES = """# 复习笔记

## 混叠

混叠：当抽样频率低于 2 fmax 时，高频分量折叠到低频，产生混叠失真。

## 信噪比

信噪比：信号功率与噪声功率之比，常以 dB 表示；均匀量化每增加 1 bit 约提升 6 dB。
"""


def main() -> int:
    _write("docs/ch01-sampling.md", CH01)
    _write("docs/ch02-quantization.md", CH02)
    _write("notes/review.md", NOTES)

    ch01_quote = _quote("docs/ch01-sampling.md", 5, 5)
    ch02_quote = _quote("docs/ch02-quantization.md", 9, 9)

    _write(
        ".memoria/sidecars/docs/ch01-sampling.memoria.yaml",
        f"""schema_version: 1
file: docs/ch01-sampling.md
knowledge_points:
- id: ch1-sampling
  name: 第1章 抽样定理
  description: 抽样定理全章（低通与带通抽样）
  range:
    start:
      snippet: '# 第1章 抽样定理'
      line_hint: 1
    end:
      snippet: '带通抽样定理：对带宽为 B 的带通信号，抽样频率 fs 必须不小于 2B，才能无失真恢复。'
      line_hint: 9
- id: ch1-lowpass
  name: 低通抽样定理
  description: 低通信号抽样频率为何必须不小于两倍最高频率
  range:
    start:
      snippet: '## 1.1 低通抽样定理'
      line_hint: 3
    end:
      snippet: '低通抽样定理：对最高频率为 fmax 的低通信号，抽样频率 fs 必须不小于 2 fmax，才能无失真恢复。'
      line_hint: 5
- id: ch1-bandpass
  name: 带通抽样定理
  description: 带通信号抽样频率为何必须不小于两倍带宽
  range:
    start:
      snippet: '## 1.2 带通抽样定理'
      line_hint: 7
    end:
      snippet: '带通抽样定理：对带宽为 B 的带通信号，抽样频率 fs 必须不小于 2B，才能无失真恢复。'
      line_hint: 9
edges:
- type: contain
  contain_kind: semantic
  source_id: ch1-sampling
  targets:
  - ch1-lowpass
  derived_by: author
  curated_by: human:fixture
  curated_at: '2026-11-04T00:00:00Z'
  assertion_source:
    file: docs/ch01-sampling.md
    line_start: 5
    line_end: 5
    quote_sha256: {ch01_quote}
""",
    )

    _write(
        ".memoria/sidecars/docs/ch02-quantization.memoria.yaml",
        f"""schema_version: 1
file: docs/ch02-quantization.md
knowledge_points:
- id: ch2-whole
  name: 第2章 量化
  description: 量化全章（均匀与非均匀量化）
  range:
    start:
      snippet: '# 第2章 量化'
      line_hint: 1
    end:
      snippet: '非均匀量化：对小信号采用小量化间隔，对大信号采用大量化间隔，以改善小信号信噪比。'
      line_hint: 11
- id: ch2-uniform
  name: 均匀量化
  description: 量化间隔处处相等的量化方式
  range:
    start:
      snippet: '## 2.1 均匀量化'
      line_hint: 5
    end:
      snippet: '均匀量化：量化间隔 Δ 处处相等，量化误差均匀分布。'
      line_hint: 7
- id: ch2-nonuniform
  name: 非均匀量化
  description: 小信号用小间隔、大信号用大间隔的量化方式
  range:
    start:
      snippet: '## 2.2 非均匀量化'
      line_hint: 9
    end:
      snippet: '非均匀量化：对小信号采用小量化间隔，对大信号采用大量化间隔，以改善小信号信噪比。'
      line_hint: 11
edges:
- type: contain
  contain_kind: semantic
  source_id: ch2-whole
  targets:
  - ch2-uniform
  derived_by: author
  curated_by: human:fixture
  curated_at: '2026-11-04T00:00:00Z'
  assertion_source:
    file: docs/ch02-quantization.md
    line_start: 9
    line_end: 9
    quote_sha256: {ch02_quote}
""",
    )

    _write(
        ".memoria/sidecars/notes/review.memoria.yaml",
        """schema_version: 1
file: notes/review.md
knowledge_points:
- id: note-aliasing
  name: 混叠
  description: 抽样频率不足时高频折叠到低频的现象
  range:
    start:
      snippet: '## 混叠'
      line_hint: 3
    end:
      snippet: '混叠：当抽样频率低于 2 fmax 时，高频分量折叠到低频，产生混叠失真。'
      line_hint: 5
- id: note-snr
  name: 信噪比
  description: 信号功率与噪声功率之比，量化 bit 数与信噪比的关系
  range:
    start:
      snippet: '## 信噪比'
      line_hint: 7
    end:
      snippet: '信噪比：信号功率与噪声功率之比，常以 dB 表示；均匀量化每增加 1 bit 约提升 6 dB。'
      line_hint: 9
""",
    )

    _write(
        ".memoria/manifest.yaml",
        """schema_version: 1
updated_at: '2026-11-04T00:00:00Z'
files: []
""",
    )

    print(f"fixture KB written: {KB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
