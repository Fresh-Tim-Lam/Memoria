#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组件命名规范校验器（comp.naming-convention，task-260 → task-264 对齐 registry v0.2）。

规则源：
  - v0.2：`docs/design/components-v0.2.md §3`（registry v2 格式与可复用判据）
  - v0.1：`docs/design/components-v0.1.md §3`（旧 registry v1 向后兼容）
唯一事实源：`docs/design/component-registry.v2.json`（v2）；v1 仍可显式 `--registry` 传入。
证据副本：registry.evidenceCopy（须 byte-identical）。

用法：
    python scripts/agent/comp_naming_convention.py                     # 默认校验 v2；exit 0/1/2
    python scripts/agent/comp_naming_convention.py --registry docs/design/component-registry.v1.json
    python scripts/agent/comp_naming_convention.py --json              # 输出契约固定 JSON
    python scripts/agent/comp_naming_convention.py --selftest

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
from pathlib import Path

DEFAULT_REGISTRY = "docs/design/component-registry.v2.json"
DEFAULT_DOCS = "docs/design/components-v0.2.md"
DEFAULT_SCHEMA = "docs/design/component-registry.schema.json"
MODE_V2 = "v2"
MODE_V1 = "v1"

ID_RE = re.compile(r"^comp\.[a-z0-9]+(-[a-z0-9]+)*$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
FILENAME_VERSION_RE = re.compile(r"\.v(\d+)\.json$")

ROOT_REQUIRED_V1 = ("schema", "registryId", "version", "updatedAt", "source", "owner",
                    "status", "namingRule", "sourceOfTruth", "canonicalPath",
                    "evidenceCopy", "summary", "components")
ROOT_REQUIRED_V2 = ("$schema", "schema", "registryId", "schemaVersion", "dataVersion",
                    "updatedAt", "source", "owner", "status", "namingRule", "sourceOfTruth",
                    "canonicalPath", "evidenceCopy", "roleTemplates", "typeVocabulary",
                    "acceptGapPolicy", "summary", "gaps", "components")
COMPONENT_REQUIRED_V1 = ("id", "version", "name", "summary", "inputs", "outputs",
                         "preconditions", "failureStates", "sideEffects", "idempotent",
                         "composesWith", "implementedBy", "status", "reuse",
                         "matchedExisting", "namingBasis")
# v2 组件必填键（与 docs/design/component-registry.schema.json $defs.component.required 一致）
COMPONENT_REQUIRED_V2 = ("id", "version", "interfaceVersion", "name", "summary", "callable",
                         "executor", "sopRef", "reuseDecision", "reuseKind", "evidence",
                         "inputs", "outputs", "preconditions", "failureStates", "sideEffects",
                         "idempotent", "composesWith", "matchedExisting", "ownerRole",
                         "writeScope", "permissions", "lifecycle", "status", "namingBasis")
SCALAR_KEYS = ("id", "version", "interfaceVersion", "name", "summary", "status", "namingBasis",
               "reuseDecision", "reuseKind", "ownerRole", "sopRef")
LIST_KEYS = ("evidence", "inputs", "outputs", "preconditions", "failureStates",
             "sideEffects", "composesWith", "matchedExisting", "writeScope", "permissions")


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


class ValidationError(Exception):
    """输入不可用（无输入/坏 JSON/坏路径）⇒ exit 2，不是 exit 0。"""


def _resolve(path_arg: str) -> Path:
    path = Path(path_arg)
    return path if path.is_absolute() else ROOT / path


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise ValidationError(f"输入文件不存在：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
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


def _mode(data: dict) -> str:
    if data.get("schema") == "component-registry/v2" or data.get("schemaVersion") or data.get("dataVersion"):
        return MODE_V2
    return MODE_V1


def _load_schema_required(schema_path: Path) -> tuple[list[str], list[str]]:
    """从 v2 JSON Schema 读取根/组件的 required 键；读不到则退回内置常量。"""
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return list(ROOT_REQUIRED_V2), list(COMPONENT_REQUIRED_V2)
    root_required = [k for k in (schema.get("required") or []) if isinstance(k, str)]
    defs = schema.get("$defs") or schema.get("definitions") or {}
    component_required = [k for k in ((defs.get("component") or {}).get("required") or [])
                          if isinstance(k, str)]
    return (root_required or list(ROOT_REQUIRED_V2),
            component_required or list(COMPONENT_REQUIRED_V2))


def validate(registry_path: Path, docs_path: Path, schema_path: Path | None = None) -> dict:
    """执行 R1–R8（v1/v2 双模式），返回 contract 字典。输入不可用抛 ValidationError。"""
    if not docs_path.is_file():
        raise ValidationError(f"规则文档不存在：{docs_path}")
    data = _read_json(registry_path)
    mode = _mode(data)
    schema_path = schema_path or (ROOT / DEFAULT_SCHEMA)
    if mode == MODE_V2 and not schema_path.is_file():
        raise ValidationError(f"v2 registry 需要 schema 文件：{schema_path}")
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
        bad("R4", None, "components 为空：无输入不得判为通过")

    # ---- R1：id 正则；R2：id 唯一 ----
    seen: dict[str, int] = {}
    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            bad("R4", None, f"components[{index}] 不是对象")
            continue
        cid = comp.get("id")
        if not isinstance(cid, str) or not ID_RE.match(cid):
            counts["badIds"] += 1
            bad("R1", cid if isinstance(cid, str) else None,
                f"components[{index}].id={cid!r} 不符合 ^comp\\.[a-z0-9]+(-[a-z0-9]+)*$")
        if isinstance(cid, str):
            seen[cid] = seen.get(cid, 0) + 1
    for cid, occurrence in sorted(seen.items()):
        if occurrence > 1:
            counts["duplicates"] += occurrence - 1
            bad("R2", cid, f"id 重复 {occurrence} 次（id 必须唯一）")

    # ---- R3：版本字段存在且与文件名/根声明一致 ----
    root_versions = {key: data.get(key) for key in ("version", "schemaVersion", "dataVersion")
                     if data.get(key) is not None}
    if not root_versions and mode == MODE_V2:
        bad("R3", None, "根版本声明缺失：v2 需 schemaVersion/dataVersion")
    if not root_versions and mode == MODE_V1:
        bad("R3", None, "根版本声明缺失：v1 需 version")
    for key, value in root_versions.items():
        if not isinstance(value, str) or not SEMVER_RE.match(value):
            counts["badVersions"] += 1
            bad("R3", None, f"根字段 {key}={value!r} 不符合 ^\\d+\\.\\d+\\.\\d+$")
    filename_match = FILENAME_VERSION_RE.search(registry_path.name)
    schema_field = str(data.get("schema") or "")
    schema_major = None
    if schema_field.startswith("component-registry/v"):
        try:
            schema_major = int(schema_field.rsplit("/v", 1)[1])
        except ValueError:
            schema_major = None
    if filename_match:
        file_major = int(filename_match.group(1))
        if schema_major is not None and schema_major != file_major:
            bad("R3", None, f"文件名 v{file_major} 与 schema={schema_field!r} 主版本不一致")
        schema_version = data.get("schemaVersion")
        if isinstance(schema_version, str) and SEMVER_RE.match(schema_version):
            if int(schema_version.split(".")[0]) != file_major:
                bad("R3", None,
                    f"schemaVersion={schema_version!r} 主版本与文件名 v{file_major} 不一致")
    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            continue
        version = comp.get("version")
        if not isinstance(version, str) or not SEMVER_RE.match(version):
            counts["badVersions"] += 1
            bad("R3", comp.get("id"),
                f"components[{index}].version={version!r} 不符合 ^\\d+\\.\\d+\\.\\d+$")

    # ---- R4：必填键非空（v2 从 schema required 读取；v1 用内置清单） ----
    if mode == MODE_V2:
        root_required, component_required = _load_schema_required(schema_path)
    else:
        root_required, component_required = list(ROOT_REQUIRED_V1), list(COMPONENT_REQUIRED_V1)
    for key in root_required:
        if not _is_nonempty(data.get(key)):
            bad("R4", None, f"registry 根必填键缺失/为空：{key}")
    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            continue
        for key in component_required:
            if key not in comp:
                bad("R4", comp.get("id"), f"components[{index}] 缺必填键：{key}")
                continue
            value = comp.get(key)
            if key in SCALAR_KEYS and not _is_nonempty(value):
                bad("R4", comp.get("id"), f"components[{index}] 必填键为空：{key}")
            elif key in LIST_KEYS and not isinstance(value, list):
                bad("R4", comp.get("id"), f"components[{index}].{key} 必须是数组")
        if mode == MODE_V1:
            inputs = comp.get("inputs")
            if isinstance(inputs, list):
                for j, item in enumerate(inputs):
                    if not isinstance(item, dict) or not _is_nonempty(item.get("name")) \
                            or not _is_nonempty(item.get("type")):
                        bad("R4", comp.get("id"),
                            f"components[{index}].inputs[{j}] 缺 name/type")

    # ---- R5：引用完整性 ----
    ids = {comp.get("id") for comp in components
           if isinstance(comp, dict) and isinstance(comp.get("id"), str)}
    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            continue
        cid = comp.get("id")
        if mode == MODE_V2:
            for ref in comp.get("composesWith") or []:
                target = ref.get("targetId") if isinstance(ref, dict) else ref
                if not isinstance(target, str) or target not in ids:
                    bad("R5", cid, f"composesWith.targetId 引用不存在：{target!r}")
            executor = comp.get("executor") if isinstance(comp.get("executor"), dict) else {}
            if executor.get("kind") == "tool" and not _is_nonempty(executor.get("entrypoint")):
                bad("R5", cid, "executor.kind=tool 但 entrypoint 缺失/为空")
            for j, item in enumerate(comp.get("matchedExisting") or []):
                ref = item.get("ref") if isinstance(item, dict) else item
                if not _is_nonempty(ref):
                    bad("R5", cid, f"matchedExisting[{j}].ref 缺失/为空")
        else:
            for ref in comp.get("composesWith") or []:
                if not isinstance(ref, str) or ref not in ids:
                    bad("R5", cid, f"composesWith 引用不存在：{ref!r}")
            impl = comp.get("implementedBy")
            if not isinstance(impl, dict) or not _is_nonempty(impl.get("ref")):
                bad("R5", cid, "implementedBy.ref 缺失/为空")
            for j, item in enumerate(comp.get("matchedExisting") or []):
                if not isinstance(item, dict) or not _is_nonempty(item.get("ref")):
                    bad("R5", cid, f"matchedExisting[{j}].ref 缺失/为空")

    # ---- R6：状态/可调用一致性（v2 用 callable+executor；v1 用 status+implementedBy） ----
    for index, comp in enumerate(components):
        if not isinstance(comp, dict):
            continue
        cid = comp.get("id")
        if mode == MODE_V2:
            if comp.get("status") not in ("implemented", "partial", "missing"):
                bad("R6", cid, f"status={comp.get('status')!r} 非法")
            if comp.get("reuseDecision") not in ("reuse", "complete", "new"):
                bad("R6", cid, f"reuseDecision={comp.get('reuseDecision')!r} 非法")
            callable_flag = comp.get("callable")
            if not isinstance(callable_flag, bool):
                bad("R6", cid, f"callable={callable_flag!r} 必须是 bool")
            executor = comp.get("executor") if isinstance(comp.get("executor"), dict) else {}
            kind = executor.get("kind")
            if callable_flag is True:
                if kind != "tool":
                    bad("R6", cid, f"callable=true 但 executor.kind={kind!r}（应为 tool）")
                for field in ("argsSchema", "returnsSchema"):
                    if not _is_nonempty(comp.get(field)):
                        bad("R6", cid, f"callable=true 但 {field} 缺失/为空")
            elif callable_flag is False:
                if kind not in ("role", "manual"):
                    bad("R6", cid, f"callable=false 但 executor.kind={kind!r}（应为 role/manual）")
                if not _is_nonempty(comp.get("sopRef")):
                    bad("R6", cid, "callable=false 但 sopRef 缺失/为空")
        else:
            status = comp.get("status")
            impl = comp.get("implementedBy") if isinstance(comp.get("implementedBy"), dict) else {}
            kind = impl.get("kind")
            if status not in ("implemented", "partial", "missing"):
                bad("R6", cid, f"status={status!r} 不在 implemented/partial/missing")
            elif status == "missing" and kind != "missing":
                bad("R6", cid, f"status=missing 但 implementedBy.kind={kind!r}（应为 missing）")
            elif status in ("implemented", "partial") and kind not in ("tool", "doc", "convention"):
                bad("R6", cid, f"status={status} 但 implementedBy.kind={kind!r}（应为 tool/doc/convention）")
            if comp.get("reuse") not in ("reuse", "complete", "new"):
                bad("R6", cid, f"reuse={comp.get('reuse')!r} 非法")

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
        canonical = (_resolve(canonical_rel) if isinstance(canonical_rel, str) and canonical_rel.strip()
                     else registry_path)
        copy_path = _resolve(copy_rel)
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
        if mode == MODE_V2:
            expected = {
                "total": len(components),
                "reuse": sum(1 for c in components if isinstance(c, dict) and c.get("reuseDecision") == "reuse"),
                "complete": sum(1 for c in components if isinstance(c, dict) and c.get("reuseDecision") == "complete"),
                "new": sum(1 for c in components if isinstance(c, dict) and c.get("reuseDecision") == "new"),
                "statusImplemented": sum(1 for c in components if isinstance(c, dict) and c.get("status") == "implemented"),
                "statusPartial": sum(1 for c in components if isinstance(c, dict) and c.get("status") == "partial"),
                "statusMissing": sum(1 for c in components if isinstance(c, dict) and c.get("status") == "missing"),
                "callable": sum(1 for c in components if isinstance(c, dict) and c.get("callable") is True),
                "manual": sum(1 for c in components if isinstance(c, dict) and c.get("callable") is False),
            }
        else:
            expected = {
                "total": len(components),
                "reuse": sum(1 for c in components if isinstance(c, dict) and c.get("reuse") == "reuse"),
                "complete": sum(1 for c in components if isinstance(c, dict) and c.get("reuse") == "complete"),
                "new": sum(1 for c in components if isinstance(c, dict) and c.get("reuse") == "new"),
                "missingPure": sum(1 for c in components if isinstance(c, dict) and c.get("status") == "missing"),
                "missingPartial": sum(1 for c in components if isinstance(c, dict) and c.get("status") == "partial"),
            }
        for key, expected_value in expected.items():
            actual = summary.get(key)
            if actual != expected_value:
                bad("R8", None, f"summary.{key}={actual!r} 与实际计数 {expected_value} 不一致")

    return {"ok": not violations, "violations": violations, "counts": counts}


# ---------------------------------------------------------------------------
# selftest：v2 主口径 + v1 向后兼容 + R1–R8 必红
# ---------------------------------------------------------------------------
def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _v2_fixture(tmp: Path, name: str, mutate=None) -> Path:
    """以真实 v2 registry 为基底造 fixture：canonical/evidence 指向 tmp 的双副本。"""
    data = json.loads((ROOT / DEFAULT_REGISTRY).read_text(encoding="utf-8-sig"))
    if mutate:
        mutate(data)
    canonical = tmp / f"fixtures/{name}.json"
    copy = tmp / f"fixtures/{name}.copy.json"
    data["canonicalPath"] = str(canonical)
    data["evidenceCopy"] = str(copy)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    _write(canonical, text)
    _write(copy, text)
    return canonical


def selftest() -> int:
    failures: list[str] = []
    if not _utf8_stdio_probe():
        failures.append("UTF-8 输出探针失败：管道下 stdout 不是 UTF-8（全角字符会 traceback）")

    docs_v2 = ROOT / DEFAULT_DOCS
    docs_v1 = ROOT / "docs/design/components-v0.1.md"

    # 绿：真实 v2 + v1（向后兼容）
    v2_result = validate(ROOT / DEFAULT_REGISTRY, docs_v2)
    if not v2_result["ok"]:
        failures.append("v2 真实 registry 应 exit 0："
                        + "; ".join(f"{v['ruleId']}:{v['detail'][:80]}" for v in v2_result["violations"]))
    v1_result = validate(ROOT / "docs/design/component-registry.v1.json", docs_v1)
    if not v1_result["ok"]:
        failures.append("v1 registry 向后兼容应 exit 0："
                        + "; ".join(f"{v['ruleId']}:{v['detail'][:80]}" for v in v1_result["violations"]))

    with __import__("tempfile").TemporaryDirectory(prefix="comp-naming-selftest-") as tmp_s:
        tmp = Path(tmp_s)

        def expect_rule(name: str, path: Path, rule_id: str) -> None:
            result = validate(path, docs_v2, ROOT / DEFAULT_SCHEMA)
            if result["ok"]:
                failures.append(f"{name}: 应 FAIL，实际 ok=true")
                return
            if not any(v["ruleId"] == rule_id for v in result["violations"]):
                failures.append(f"{name}: 未命中 {rule_id}，实际 "
                                f"{sorted({v['ruleId'] for v in result['violations']})}")

        # R1/R2/R3
        expect_rule("R1-uppercase-id",
                    _v2_fixture(tmp, "r1", lambda d: d["components"][0].__setitem__("id", "comp.Bad-ID")),
                    "R1")
        def _dup(d):
            d["components"][1]["id"] = d["components"][0]["id"]
        expect_rule("R2-duplicate-id", _v2_fixture(tmp, "r2", _dup), "R2")
        expect_rule("R3-bad-component-version",
                    _v2_fixture(tmp, "r3", lambda d: d["components"][0].__setitem__("version", "1.0")), "R3")
        expect_rule("R3-missing-root-version",
                    _v2_fixture(tmp, "r3b", lambda d: [d.pop("schemaVersion", None), d.pop("dataVersion", None)]),
                    "R3")
        # R4：缺必填键 / 空 components
        expect_rule("R4-missing-key",
                    _v2_fixture(tmp, "r4", lambda d: d["components"][0].pop("sopRef", None)), "R4")
        def _empty(d):
            d["components"] = []
            d["summary"] = {"total": 0, "reuse": 0, "complete": 0, "new": 0,
                            "statusImplemented": 0, "statusPartial": 0, "statusMissing": 0,
                            "callable": 0, "manual": 0}
        expect_rule("R4-empty-components", _v2_fixture(tmp, "r4-empty", _empty), "R4")
        # R5：composesWith.targetId 不存在
        def _badref(d):
            d["components"][0]["composesWith"] = [{"targetId": "comp.not-exist", "mapping": []}]
        expect_rule("R5-bad-ref", _v2_fixture(tmp, "r5", _badref), "R5")
        # R6：callable=true 但 executor.kind=role
        def _badcallable(d):
            d["components"][0]["callable"] = True
            d["components"][0]["executor"] = {"kind": "role", "entrypoint": ""}
        expect_rule("R6-callable-mismatch", _v2_fixture(tmp, "r6", _badcallable), "R6")
        # R7：双副本不等
        r7_path = _v2_fixture(tmp, "r7", None)
        r7_data = json.loads(r7_path.read_text(encoding="utf-8"))
        _write(Path(r7_data["evidenceCopy"]), json.dumps({"different": True}, ensure_ascii=False))
        r7_result = validate(r7_path, docs_v2, ROOT / DEFAULT_SCHEMA)
        if r7_result["ok"] or r7_result["counts"]["copyMismatch"] is not True:
            failures.append("R7-copy-mismatch: 应 FAIL 且 counts.copyMismatch=true")
        # R8：summary 计数不一致
        expect_rule("R8-summary-mismatch",
                    _v2_fixture(tmp, "r8", lambda d: d["summary"].__setitem__("total", 99)), "R8")
        # 无输入：registry/docs 缺失 ⇒ ValidationError（exit 2）
        for label, args in (("no-registry", (tmp / "no-such-registry.json", docs_v2)),
                            ("no-docs", (ROOT / DEFAULT_REGISTRY, tmp / "no-such-docs.md"))):
            try:
                validate(*args)
                failures.append(f"{label}: 缺失输入时必须报错，实际未抛")
            except ValidationError:
                pass

    if failures:
        print("SELFTEST FAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("SELFTEST PASS：v2 真实 registry + v1 向后兼容均 exit 0；"
          "R1/R2/R3(坏 version/缺根版本)/R4(缺键/空 components)/R5(targetId)/R6(callable)/R7(副本不等)/R8(summary) 各自必红；"
          "无输入（registry/docs 缺失）必报错（不空过）。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="组件命名规范校验器（comp.naming-convention）")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help="registry 路径（默认 v2 唯一事实源）")
    parser.add_argument("--docs", default=DEFAULT_DOCS, help="规则文档路径")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA, help="v2 JSON Schema 路径")
    parser.add_argument("--json", action="store_true", help="输出 JSON（默认即 JSON）")
    parser.add_argument("--selftest", action="store_true", help="运行必红/必绿 fixture 自测")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    registry_path = _resolve(args.registry)
    docs_path = _resolve(args.docs)
    schema_path = _resolve(args.schema)
    try:
        result = validate(registry_path, docs_path, schema_path)
    except ValidationError as exc:
        print(json.dumps({"ok": False, "error": "no-input-or-invalid", "detail": str(exc)},
                         ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
