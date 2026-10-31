#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组件 registry 查询工具（comp.component-registry，task-261）。

依赖 TD-01 校验器（`comp_naming_convention.py`，task-260）：**加载前先校验，校验失败拒载**。

用法：
    python scripts/agent/comp_component_registry.py --list
    python scripts/agent/comp_component_registry.py --id comp.task-classifier
    python scripts/agent/comp_component_registry.py --list --json        # 输出契约固定 JSON
    python scripts/agent/comp_component_registry.py --selftest

输出：
    --list → JSON 数组 [{id, name, status, reuse, implementedBy.kind}]
    --id   → 完整组件对象（JSON）
退出码：
    0 成功；1 registry 校验失败（REGISTRY_INVALID，拒载）；2 无输入/用法错误/UNKNOWN_COMPONENT。
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

def _configure_utf8_stdio() -> None:
    """管道/重定向下 stdout 可能是 cp1252 等非 UTF-8 编码：统一转 UTF-8，避免全角字符 traceback。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _utf8_stdio_probe() -> bool:
    """selftest 内部断言：对自身输出做 UTF-8 写入不抛异常（防回归）。"""
    try:
        sys.stdout.write("UTF-8 探针：✓\n")
        sys.stdout.flush()
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False
    return (sys.stdout.encoding or "").lower().replace("-", "") == "utf8"


_configure_utf8_stdio()

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from comp_naming_convention import ValidationError, validate
except Exception as exc:  # pragma: no cover - 依赖缺失必须显式失败
    print(json.dumps({"ok": False, "error": "TD01_UNAVAILABLE", "detail": str(exc)},
                     ensure_ascii=False, indent=2))
    raise SystemExit(2)

DEFAULT_REGISTRY = "docs/design/component-registry.v1.json"
DEFAULT_DOCS = "docs/design/components-v0.1.md"


class RegistryInvalid(Exception):
    def __init__(self, violations: list[dict]):
        super().__init__("registry 校验失败")
        self.violations = violations


class UnknownComponent(Exception):
    def __init__(self, component_id: str):
        super().__init__(component_id)
        self.component_id = component_id


def _resolve(path_arg: str) -> Path:
    path = Path(path_arg)
    return path if path.is_absolute() else ROOT / path


def load_registry(registry: str = DEFAULT_REGISTRY, docs: str = DEFAULT_DOCS) -> dict:
    """先跑 TD-01；通过才返回 registry。无输入抛 ValidationError，坏 registry 抛 RegistryInvalid。"""
    registry_path = _resolve(registry)
    docs_path = _resolve(docs)
    result = validate(registry_path, docs_path)  # ValidationError：无输入/坏 JSON/坏 docs
    if not result["ok"]:
        raise RegistryInvalid(result["violations"])
    return json.loads(registry_path.read_text(encoding="utf-8"))


def list_components(data: dict) -> list[dict]:
    rows = []
    for comp in data.get("components") or []:
        impl = comp.get("implementedBy") or {}
        rows.append({
            "id": comp.get("id"),
            "name": comp.get("name"),
            "status": comp.get("status"),
            "reuse": comp.get("reuse"),
            "implementedBy.kind": impl.get("kind"),
        })
    return rows


def get_component(data: dict, component_id: str) -> dict:
    for comp in data.get("components") or []:
        if comp.get("id") == component_id:
            return comp
    raise UnknownComponent(component_id)


def selftest() -> int:
    failures: list[str] = []
    if not _utf8_stdio_probe():
        failures.append("UTF-8 输出探针失败：管道下 stdout 不是 UTF-8（全角字符会 traceback）")
    with tempfile.TemporaryDirectory(prefix="comp-registry-selftest-") as tmp_s:
        tmp = Path(tmp_s)
        docs = tmp / "docs/design/components-v0.1.md"
        docs.parent.mkdir(parents=True, exist_ok=True)
        docs.write_text("# rules\n", encoding="utf-8")
        real = json.loads((ROOT / DEFAULT_REGISTRY).read_text(encoding="utf-8"))

        def fixture(name: str, mutate=None) -> tuple[Path, Path]:
            data = json.loads(json.dumps(real, ensure_ascii=False))
            if mutate:
                mutate(data)
            canonical = tmp / f"fixtures/{name}.json"
            copy = tmp / f"fixtures/{name}.copy.json"
            data["canonicalPath"] = str(canonical)
            data["evidenceCopy"] = str(copy)
            canonical.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            canonical.write_text(text, encoding="utf-8", newline="\n")
            copy.write_text(text, encoding="utf-8", newline="\n")
            return canonical, copy

        green, _ = fixture("green")
        data = load_registry(str(green), str(docs))
        rows = list_components(data)
        if len(rows) != 17:
            failures.append(f"list: 期望 17 行，实际 {len(rows)}")
        counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("implemented", "partial", "missing")}
        # 与 registry summary 的 status 计数交叉核对（acceptance: implemented 4 / partial 9 / missing 4）
        if counts != {"implemented": 4, "partial": 9, "missing": 4}:
            failures.append(f"list: status 计数应为 implemented=4/partial=9/missing=4，实际 {counts}")
        task_cls = get_component(data, "comp.task-classifier")
        if not task_cls.get("inputs") or not all(i.get("name") for i in task_cls["inputs"]):
            failures.append("--id comp.task-classifier: inputs[].name 存在空值")
        if not task_cls.get("id") or not task_cls.get("version"):
            failures.append("--id comp.task-classifier: 缺 id/version")

        # unknown id
        try:
            get_component(data, "comp.not-exist")
            failures.append("unknown-id：应抛 UNKNOWN_COMPONENT，实际未抛")
        except UnknownComponent:
            pass

        # TD-01 拒载：坏 registry（大写 id）不得静默加载
        bad, _ = fixture("bad-id", lambda d: d["components"][0].__setitem__("id", "comp.Bad-ID"))
        try:
            load_registry(str(bad), str(docs))
            failures.append("TD-01 拒载：坏 registry 被静默加载了")
        except RegistryInvalid:
            pass
        # 无输入：registry 缺失 ⇒ ValidationError
        try:
            load_registry(str(tmp / "no-such.json"), str(docs))
            failures.append("no-input：缺失 registry 未报错")
        except ValidationError:
            pass

    if failures:
        print("SELFTEST FAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("SELFTEST PASS：--list 17 行 & status 计数(4/9/4) 与 summary 一致；--id 返回全字段且 inputs 非空；"
          "未知 id 抛 UNKNOWN_COMPONENT（exit 2）；坏 registry 被 TD-01 拒载（不静默加载）；无输入报错。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="组件 registry 查询工具（comp.component-registry）")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY)
    parser.add_argument("--docs", default=DEFAULT_DOCS)
    parser.add_argument("--list", action="store_true", help="列出全部组件摘要")
    parser.add_argument("--id", dest="component_id", help="按 id 查询完整组件对象")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认即 JSON）")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.list and not args.component_id:
        print(json.dumps({"ok": False, "error": "no-input", "detail": "需要 --list 或 --id（无输入不得判过）"},
                         ensure_ascii=False, indent=2))
        return 2
    try:
        data = load_registry(args.registry, args.docs)
    except ValidationError as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    except RegistryInvalid as exc:
        print(json.dumps({"ok": False, "error": "REGISTRY_INVALID",
                          "violations": exc.violations}, ensure_ascii=False, indent=2))
        return 1
    try:
        if args.list:
            print(json.dumps(list_components(data), ensure_ascii=False, indent=2))
        else:
            print(json.dumps(get_component(data, args.component_id), ensure_ascii=False, indent=2))
    except UnknownComponent as exc:
        print(json.dumps({"ok": False, "error": "UNKNOWN_COMPONENT",
                          "componentId": exc.component_id}, ensure_ascii=False, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
