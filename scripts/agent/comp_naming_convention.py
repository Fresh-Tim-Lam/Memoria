#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组件命名规范校验器（comp.naming-convention，task-260）。

规则源：`docs/design/components-v0.1.md §3` 的 R1–R8（设计资产，待人类批准升 conventions）。
唯一事实源：`docs/design/component-registry.v1.json`；证据副本：registry.evidenceCopy（须 byte-identical）。

用法：
    python scripts/agent/comp_naming_convention.py                     # 对默认 registry 校验；exit 0/1/2
    python scripts/agent/comp_naming_convention.py --json              # 同上（输出契约固定为 JSON）
    python scripts/agent/comp_naming_convention.py --registry <path> --docs <path>
    python scripts/agent/comp_naming_convention.py --selftest          # 必红/必绿 fixture 自测

输出契约（stdout JSON）：
    {"ok": bool,
     "violations": [{"ruleId": "R1".."R8", "componentId": str|null, "detail": str}],
     "counts": {"components": int, "duplicates": int, "badIds": int,
                "badVersions": int, "copyMismatch": bool}}
退出码：0=全过；1=有 violation；2=无输入/用法错误（绝不"没输入=通过"）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
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
DEFAULT_REGISTRY = "docs/design/component-registry.v1.json"
DEFAULT_DOCS = "docs/design/components-v0.1.md"

ID_RE = re.compile(r"^comp\.[a-z0-9]+(-[a-z0-9]+)*$")
CLS_RE = re.compile(r"^cls\.[a-z0-9]+(-[a-z0-9]+)*$")
META_RE = re.compile(r"^meta\.[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

ROOT_REQUIRED = ("schema", "registryId", "version", "updatedAt", "source", "owner",
                 "status", "namingRule", "sourceOfTruth", "canonicalPath",
                 "evidenceCopy", "summary", "components")
COMPONENT_REQUIRED = ("id", "version", "name", "summary", "inputs", "outputs",
                      "preconditions", "failureStates", "sideEffects", "idempotent",
                      "composesWith", "implementedBy", "status", "reuse",
                      "matchedExisting", "namingBasis")
# R4 的"非空"只约束标量/对象键；数组键（preconditions/composesWith/matchedExisting 等）可空但必须存在。
COMPONENT_REQUIRED_SCALAR = ("id", "version", "name", "summary", "idempotent",
                             "implementedBy", "status", "reuse", "namingBasis")
COMPONENT_REQUIRED_LIST = ("preconditions", "failureStates", "sideEffects",
                           "composesWith", "matchedExisting")
INPUT_REQUIRED = ("name", "type")
IMPLEMENTED_KINDS = {"tool", "doc", "convention", "missing"}
COMPONENT_STATUS = {"implemented", "partial", "missing"}
REUSE_VALUES = {"reuse", "complete", "new"}


class ValidationError(Exception):
    """输入不可用（无输入/坏 JSON/坏路径）⇒ exit 2，不是 exit 0。"""


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise ValidationError(f"输入文件不存在：{path}")
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"输入无法解析（{path}）：{exc}")
    if not isinstance(data, dict):
        raise ValidationError(f"registry 根必须是 JSON 对象：{path}")
    return data


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_nonempty(value) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return value is not None


def validate(registry_path: Path, docs_path: Path) -> dict:
    """执行 R1–R8，返回 contract 字典。输入不可用抛 ValidationError。"""
    if not docs_path.is_file():
        raise ValidationError(f"规则文档不存在：{docs_path}")
    data = _read_json(registry_path)
    violations: list[dict] = []
    counts = {"components": 0, "duplicates": 0, "badIds": 0,
              "badVersions": 0, "copyMismatch": False}

    def bad(rule_id: str, component_id, detail: str) -> None:
        violations.append({"ruleId": rule_id, "componentId": component_id, "detail": detail})

    components = data.get("components")
    if not isinstance(components, list):
        raise ValidationError("registry.components 不是数组（无输入不得判过）")
    counts["components"] = len(components)
    if not components:
        # 空输入 ≠ 通过（R4：根必填键 components 非空）
        bad("R4", None, "components 为空：无输入不得判为通过")

    # ---- R1：id 正则；R2：id 唯一；R3：版本 semver ----
    seen: dict[str, int] = {}
    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            bad("R4", None, f"components[{index}] 不是对象")
            continue
        cid = comp.get("id")
        cid_str = str(cid) if isinstance(cid, str) else str(cid)
        if not isinstance(cid, str) or not ID_RE.match(cid):
            counts["badIds"] += 1
            bad("R1", cid if isinstance(cid, str) else None,
                f"components[{index}].id={cid!r} 不符合 ^comp\\.[a-z0-9]+(-[a-z0-9]+)*$")
        if isinstance(cid, str):
            seen[cid] = seen.get(cid, 0) + 1
        version = comp.get("version")
        if not isinstance(version, str) or not SEMVER_RE.match(version):
            counts["badVersions"] += 1
            bad("R3", cid if isinstance(cid, str) else None,
                f"components[{index}].version={version!r} 不符合 ^\\d+\\.\\d+\\.\\d+$")

    for cid, occurrence in sorted(seen.items()):
        if occurrence > 1:
            counts["duplicates"] += occurrence - 1
            bad("R2", cid, f"id 重复 {occurrence} 次（id 必须唯一）")

    root_version = data.get("version")
    if not isinstance(root_version, str) or not SEMVER_RE.match(root_version):
        counts["badVersions"] += 1
        bad("R3", None, f"registry.version={root_version!r} 不符合 ^\\d+\\.\\d+\\.\\d+$")

    # ---- R4：根/组件必填键非空 ----
    for key in ROOT_REQUIRED:
        if not _is_nonempty(data.get(key)):
            bad("R4", None, f"registry 根必填键缺失/为空：{key}")
    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            continue
        for key in COMPONENT_REQUIRED:
            if key not in comp:
                bad("R4", comp.get("id"), f"components[{index}] 缺必填键：{key}")
                continue
            if key in COMPONENT_REQUIRED_SCALAR and not _is_nonempty(comp.get(key)):
                bad("R4", comp.get("id"), f"components[{index}] 必填键为空：{key}")
            elif key in ("inputs", "outputs"):
                value = comp.get(key)
                if not isinstance(value, list) or not value:
                    bad("R4", comp.get("id"), f"components[{index}].{key} 必须是非空数组")
            elif key in COMPONENT_REQUIRED_LIST and not isinstance(comp.get(key), list):
                bad("R4", comp.get("id"), f"components[{index}].{key} 必须是数组")
        # inputs[] 元素形状
        inputs = comp.get("inputs")
        if isinstance(inputs, list):
            for j, item in enumerate(inputs):
                if not isinstance(item, dict):
                    bad("R4", comp.get("id"), f"components[{index}].inputs[{j}] 不是对象")
                    continue
                for key in INPUT_REQUIRED:
                    if not _is_nonempty(item.get(key)):
                        bad("R4", comp.get("id"),
                            f"components[{index}].inputs[{j}] 缺必填键或为空：{key}")

    # ---- R5：引用完整性 ----
    ids = {comp.get("id") for comp in components
           if isinstance(comp, dict) and isinstance(comp.get("id"), str)}
    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            continue
        cid = comp.get("id")
        for ref in comp.get("composesWith") or []:
            if not isinstance(ref, str) or ref not in ids:
                bad("R5", cid, f"composesWith 引用不存在：{ref!r}")
        impl = comp.get("implementedBy")
        if not isinstance(impl, dict) or not _is_nonempty(impl.get("ref")):
            bad("R5", cid, "implementedBy.ref 缺失/为空")
        for j, item in enumerate(comp.get("matchedExisting") or []):
            if not isinstance(item, dict) or not _is_nonempty(item.get("ref")):
                bad("R5", cid, f"matchedExisting[{j}].ref 缺失/为空")

    # ---- R6：状态一致性 ----
    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            continue
        cid = comp.get("id")
        status = comp.get("status")
        impl = comp.get("implementedBy") if isinstance(comp.get("implementedBy"), dict) else {}
        kind = impl.get("kind")
        if status not in COMPONENT_STATUS:
            bad("R6", cid, f"status={status!r} 不在 {sorted(COMPONENT_STATUS)}")
        elif status == "missing" and kind != "missing":
            bad("R6", cid, f"status=missing 但 implementedBy.kind={kind!r}（应为 missing）")
        elif status in ("implemented", "partial") and kind not in ("tool", "doc", "convention"):
            bad("R6", cid, f"status={status} 但 implementedBy.kind={kind!r}（应为 tool/doc/convention）")
        reuse = comp.get("reuse")
        if reuse not in REUSE_VALUES:
            bad("R6", cid, f"reuse={reuse!r} 不在 {sorted(REUSE_VALUES)}")
        if kind is not None and kind not in IMPLEMENTED_KINDS:
            bad("R6", cid, f"implementedBy.kind={kind!r} 不在 {sorted(IMPLEMENTED_KINDS)}")

    # ---- R7：双副本一致（byte-identical） ----
    canonical_rel = data.get("canonicalPath")
    copy_rel = data.get("evidenceCopy")
    if not isinstance(canonical_rel, str) or not canonical_rel.strip():
        bad("R7", None, "registry.canonicalPath 缺失/为空，无法定位唯一事实源")
        counts["copyMismatch"] = True
    if not isinstance(copy_rel, str) or not copy_rel.strip():
        bad("R7", None, "registry.evidenceCopy 缺失/为空，无法核对证据副本")
        counts["copyMismatch"] = True
    if isinstance(copy_rel, str) and copy_rel.strip():
        canonical = registry_path if not isinstance(canonical_rel, str) or not canonical_rel.strip() \
            else (ROOT / canonical_rel.replace("\\", "/"))
        copy_path = ROOT / copy_rel.replace("\\", "/")
        if not canonical.is_file():
            bad("R7", None, f"canonicalPath 不存在：{canonical}")
            counts["copyMismatch"] = True
        elif not copy_path.is_file():
            bad("R7", None, f"evidenceCopy 不存在：{copy_path}")
            counts["copyMismatch"] = True
        elif _sha256(canonical) != _sha256(copy_path):
            counts["copyMismatch"] = True
            bad("R7", None,
                f"双副本 SHA-256 不等：{canonical_rel} vs {copy_rel}（证据副本须 byte-identical）")

    # ---- R8：根 summary 与实际数组计数一致 ----
    summary = data.get("summary")
    if not isinstance(summary, dict):
        bad("R8", None, "registry.summary 缺失/不是对象")
    else:
        reuse_n = sum(1 for c in components if isinstance(c, dict) and c.get("reuse") == "reuse")
        complete_n = sum(1 for c in components if isinstance(c, dict) and c.get("reuse") == "complete")
        new_n = sum(1 for c in components if isinstance(c, dict) and c.get("reuse") == "new")
        missing_pure_n = sum(1 for c in components if isinstance(c, dict) and c.get("status") == "missing")
        missing_partial_n = sum(1 for c in components if isinstance(c, dict) and c.get("status") == "partial")
        expected = {"total": len(components), "reuse": reuse_n, "complete": complete_n,
                    "new": new_n, "missingPure": missing_pure_n, "missingPartial": missing_partial_n}
        for key, expected_value in expected.items():
            actual = summary.get(key)
            if actual != expected_value:
                bad("R8", None, f"summary.{key}={actual!r} 与实际计数 {expected_value} 不一致")

    return {"ok": not violations, "violations": violations, "counts": counts}


# ---------------------------------------------------------------------------
# selftest：必红/必绿 fixture
# ---------------------------------------------------------------------------
def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _base_registry() -> dict:
    comp = {
        "id": "comp.test-component", "version": "0.1.0", "name": "测试组件",
        "summary": "用于 fixture", "inputs": [{"name": "x", "type": "text", "required": True}],
        "outputs": [{"name": "y", "type": "text"}], "preconditions": ["p"],
        "failureStates": ["F1"], "sideEffects": ["none"], "idempotent": True,
        "composesWith": ["comp.other-component"], "implementedBy": {"kind": "tool", "ref": "scripts/x.py"},
        "status": "implemented", "reuse": "new", "matchedExisting": [],
        "namingBasis": "components-v0.1 §2.1",
    }
    other = {
        "id": "comp.other-component", "version": "0.1.0", "name": "另一组件",
        "summary": "用于 fixture", "inputs": [{"name": "x", "type": "text"}],
        "outputs": [{"name": "y", "type": "text"}], "preconditions": ["p"],
        "failureStates": ["F1"], "sideEffects": ["none"], "idempotent": True,
        "composesWith": [], "implementedBy": {"kind": "doc", "ref": "docs/x.md"},
        "status": "partial", "reuse": "reuse", "matchedExisting": [],
        "namingBasis": "components-v0.1 §2.1",
    }
    return {
        "schema": "component-registry/v1", "registryId": "fixture", "version": "0.1.0",
        "updatedAt": "2026-10-31T00:00:00+08:00", "source": "fixture",
        "owner": "steward", "status": "fixture",
        "namingRule": {"componentId": "comp.kebab", "note": "fixture", "anchors": ["docs/design/components-v0.1.md"]},
        "sourceOfTruth": "docs/design/components-v0.1.md",
        "canonicalPath": "docs/design/component-registry.v1.json",
        "evidenceCopy": "artifacts/agent/plugin-design/component-registry.v1.json",
        "summary": {"total": 2, "reuse": 1, "complete": 0, "new": 1,
                    "missingPure": 0, "missingPartial": 1},
        "components": [comp, other],
    }


def selftest() -> int:
    failures: list[str] = []
    if not _utf8_stdio_probe():
        failures.append("UTF-8 输出探针失败：管道下 stdout 不是 UTF-8（全角字符会 traceback）")
    with tempfile.TemporaryDirectory(prefix="comp-naming-selftest-") as tmp_s:
        tmp = Path(tmp_s)
        docs = tmp / "docs/design/components-v0.1.md"
        _write(docs, "# rules\n")
        canonical = tmp / "docs/design/component-registry.v1.json"
        copy = tmp / "artifacts/agent/plugin-design/component-registry.v1.json"

        def write_registry(name: str, mutate) -> Path:
            data = _base_registry()
            mutate(data) if mutate else None
            path = tmp / f"fixtures/{name}.json"
            copy_path = tmp / f"fixtures/{name}.copy.json"
            # 双副本：canonical=registy 文件，evidence=独立副本（初始 byte-identical）
            data["canonicalPath"] = str(path)
            data["evidenceCopy"] = str(copy_path)
            payload = json.dumps(data, ensure_ascii=False, indent=2)
            _write(path, payload)
            _write(copy_path, payload)
            return path

        def expect_rule(name: str, path: Path, rule_id: str) -> None:
            result = validate(path, docs)
            if result["ok"]:
                failures.append(f"{name}: 应 FAIL，实际 ok=true")
                return
            hit = [v for v in result["violations"] if v["ruleId"] == rule_id]
            if not hit:
                failures.append(f"{name}: 未命中 {rule_id}，实际 {sorted({v['ruleId'] for v in result['violations']})}")

        # 绿：合法 fixture（双副本指向同一文件 ⇒ R7 通过）
        green = write_registry("green", None)
        result = validate(green, docs)
        if not result["ok"]:
            failures.append("绿色 fixture 误报："
                            + "; ".join(f"{v['ruleId']}:{v['detail'][:80]}" for v in result["violations"]))

        # R1 红：大写 id
        expect_rule("R1-uppercase-id", write_registry("r1", lambda d: d["components"][0].__setitem__("id", "comp.Bad-ID")), "R1")
        # R2 红：重复 id
        def _dup(d):
            d["components"][1]["id"] = "comp.test-component"
            d["summary"]["total"] = 2
        expect_rule("R2-duplicate-id", write_registry("r2", _dup), "R2")
        # R3 红：坏 version
        expect_rule("R3-bad-version", write_registry("r3", lambda d: d["components"][0].__setitem__("version", "1.0")), "R3")
        # R4 红：组件缺必填键
        expect_rule("R4-missing-key", write_registry("r4", lambda d: d["components"][0].pop("namingBasis", None)), "R4")
        # R4 红：空 components（无输入不得判过）
        def _empty(d):
            d["components"] = []
            d["summary"] = {"total": 0, "reuse": 0, "complete": 0, "new": 0,
                            "missingPure": 0, "missingPartial": 0}
        expect_rule("R4-empty-components", write_registry("r4-empty", _empty), "R4")
        # R5 红：composesWith 引用不存在
        def _badref(d):
            d["components"][0]["composesWith"] = ["comp.not-exist"]
        expect_rule("R5-bad-ref", write_registry("r5", _badref), "R5")
        # R6 红：status=missing 但 kind=tool
        def _badstatus(d):
            d["components"][0]["status"] = "missing"
            d["components"][0]["implementedBy"] = {"kind": "tool", "ref": "x"}
            d["summary"] = {"total": 2, "reuse": 1, "complete": 0, "new": 1,
                            "missingPure": 1, "missingPartial": 1}
        expect_rule("R6-status-mismatch", write_registry("r6", _badstatus), "R6")
        # R7 红：双副本内容不等（改副本文件）
        r7_path = write_registry("r7", None)
        r7_data = json.loads(r7_path.read_text(encoding="utf-8"))
        copy_path = Path(r7_data["evidenceCopy"])
        _write(copy_path, json.dumps({"different": True}, ensure_ascii=False))
        result = validate(r7_path, docs)
        if result["ok"]:
            failures.append("R7-copy-mismatch: 应 FAIL，实际 ok=true")
        if result["counts"]["copyMismatch"] is not True:
            failures.append("R7-copy-mismatch: counts.copyMismatch 应为 true")
        if not any(v["ruleId"] == "R7" for v in result["violations"]):
            failures.append("R7-copy-mismatch: 未命中 R7")
        # R8 红：summary 计数不一致
        def _badsum(d):
            d["summary"]["total"] = 99
        expect_rule("R8-summary-mismatch", write_registry("r8", _badsum), "R8")
        # 无输入：registry 不存在 ⇒ ValidationError ⇒ exit 2（由 main 体现；此处断言抛错）
        try:
            validate(tmp / "no-such-registry.json", docs)
            failures.append("no-input: 缺失 registry 时必须报错，实际未抛")
        except ValidationError:
            pass
        # 无输入：docs 不存在 ⇒ 报错
        try:
            validate(green, tmp / "no-such-docs.md")
            failures.append("no-input-docs: 缺失文档时必须报错，实际未抛")
        except ValidationError:
            pass

    if failures:
        print("SELFTEST FAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("SELFTEST PASS：R1/R2/R3/R4(缺键/空 components)/R5/R6/R7(副本不等)/R8 各自必红；"
          "合法 fixture 必绿；无输入（registry/docs 缺失）必报错（不空过）。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="组件命名规范校验器（comp.naming-convention）")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help="registry 路径（默认唯一事实源）")
    parser.add_argument("--docs", default=DEFAULT_DOCS, help="规则文档路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认即 JSON；保留兼容）")
    parser.add_argument("--selftest", action="store_true", help="运行必红/必绿 fixture 自测")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    registry_path = Path(args.registry)
    if not registry_path.is_absolute():
        registry_path = ROOT / registry_path
    docs_path = Path(args.docs)
    if not docs_path.is_absolute():
        docs_path = ROOT / docs_path
    try:
        result = validate(registry_path, docs_path)
    except ValidationError as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
