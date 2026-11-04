"""I-13 `SchemaValidator`：契约 JSON schema 的唯一校验入口（fail-closed）。

## 为什么不用 `jsonschema`

`jsonschema` **不是本项目依赖**（`pyproject.toml` 只有 PyYAML；`src/**` 从未 import 它）。
用户机/打包态不能保证它有 ⇒ 本模块实现一个**零依赖**的 JSON Schema 子集校验器，
只支持契约 schema 实际用到的关键字，**遇到不支持的关键字一律判失败**（fail-closed，
对应 S6 §S6-9「无静默」）而不是悄悄跳过。

## 契约绑定（S6 sha）

每个 schema 文件带 ``x-contract-sources``：`{冻结文档名: 期望 sha256}`。
``verify_contract_binding()`` 对**磁盘上真实的冻结文档**重算 sha 比对 —— 文档被改
而 schema 没跟 ⇒ 绑定失败（R3「契约实现漂移」的第一道闸）。

## fail-closed 清单（任一命中 ⇒ 不可用，绝不"降级为通过"）

| 情形 | 处置 |
|---|---|
| schema 名未知 | ``GRAPH_INTERNAL`` |
| schema 文件缺失/非 JSON 对象 | ``GRAPH_INTERNAL`` |
| ``x-contract-sources`` sha 与冻结文档不符 | ``GRAPH_INTERNAL`` |
| ``x-failure-code`` 不是已知 canonical 码 | ``GRAPH_INTERNAL`` |
| schema 含**不支持**的关键字 | 校验结果 not ok（不跳过） |
| 实例不合 schema | 按 ``x-failure-code`` 报错（edge→``GRAPH_EDGE_INVALID`` / kp→``GRAPH_KP_INVALID``） |
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from memoria.graph.multilevel.errors import GRAPH_INTERNAL, ERROR_SPECS, GraphError

#: 契约 schema 目录：`src/memoria/graph/contracts/schemas/`
SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "contracts" / "schemas"

#: 冻结文档所在目录：`docs/design/multilevel-graph/`
_FROZEN_DOCS_DIR = Path(__file__).resolve().parents[4] / "docs" / "design" / "multilevel-graph"

#: schema 名 → 文件名（只认这些；其余 fail-closed）
SCHEMA_FILES: dict[str, str] = {
    "edge": "edge.json",
    "kp": "kp.json",
    "datasource": "datasource.json",
    "error": "error.json",
}

#: 校验器**支持**的关键字（覆盖契约 schema 全部用法）。
SUPPORTED_KEYWORDS: frozenset[str] = frozenset({
    "type", "required", "properties", "additionalProperties", "items",
    "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum",
    "enum", "const", "pattern", "$ref", "$defs", "oneOf", "anyOf", "allOf", "not",
})

#: 纯注解关键字（不参与校验，允许出现，**不算**不支持）。
ANNOTATION_KEYWORDS: frozenset[str] = frozenset({
    "$schema", "$id", "$comment", "title", "description", "default", "examples",
    "deprecated", "readOnly", "writeOnly",
    "x-failure-code", "x-contract-sources", "x-relation-min",
})


@dataclass(frozen=True)
class ValidationError:
    """一条校验失败记录（`path` 用 JSON Pointer 风格的 `$.a[0].b`）。"""

    path: str
    message: str
    code: str

    def to_dict(self) -> dict:
        return {"path": self.path, "message": self.message, "code": self.code}


@dataclass
class ValidationResult:
    """校验结果；``ok=False`` 时 ``errors`` 必非空。"""

    ok: bool
    schema_name: str
    errors: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "schema": self.schema_name,
            "errors": [e.to_dict() for e in self.errors],
        }

    @property
    def codes(self) -> list[str]:
        seen: list[str] = []
        for e in self.errors:
            if e.code not in seen:
                seen.append(e.code)
        return seen


# ── schema 装载与契约绑定 ──────────────────────────────────────────────────


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_schema(name: str) -> dict:
    """按名装载 schema；任何异常态 ⇒ ``GraphError(GRAPH_INTERNAL)``（fail-closed）。"""
    filename = SCHEMA_FILES.get(name)
    if filename is None:
        raise GraphError(
            GRAPH_INTERNAL,
            f"未知 schema 名：{name!r}（已知：{sorted(SCHEMA_FILES)}）",
            detail={"schema_name": str(name), "known": sorted(SCHEMA_FILES)},
        )
    path = SCHEMAS_DIR / filename
    if not path.is_file():
        raise GraphError(GRAPH_INTERNAL, f"schema 文件缺失：{path}",
                         detail={"schema_name": name, "path": str(path)})
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphError(GRAPH_INTERNAL, f"schema 无法解析：{filename}: {exc}",
                         detail={"schema_name": name}) from exc
    if not isinstance(data, dict):
        raise GraphError(GRAPH_INTERNAL, f"schema 必须是 JSON 对象：{filename}",
                         detail={"schema_name": name})
    return data


def schema_failure_code(schema: dict) -> str:
    """取 schema 声明的失败码；缺失或非已知 canonical ⇒ fail-closed。"""
    code = schema.get("x-failure-code")
    if code is None:
        raise GraphError(GRAPH_INTERNAL, "schema 缺 x-failure-code（fail-closed）",
                         detail={"schema": schema.get("$id")})
    if code not in ERROR_SPECS:
        raise GraphError(
            GRAPH_INTERNAL,
            f"schema x-failure-code 不是已知 canonical 码：{code!r}",
            detail={"schema": schema.get("$id"), "code": str(code)},
        )
    return str(code)


def contract_binding_problems(schema: dict) -> list[str]:
    """比对 ``x-contract-sources`` 与磁盘冻结文档 sha；返回问题列表（空 = 绑定成立）。"""
    problems: list[str] = []
    sources = schema.get("x-contract-sources")
    if not isinstance(sources, dict) or not sources:
        return ["schema 缺 x-contract-sources（无法做 S6 sha 绑定）"]
    for doc_name, expected in sorted(sources.items()):
        doc_path = _FROZEN_DOCS_DIR / str(doc_name)
        if not doc_path.is_file():
            problems.append(f"冻结文档缺失：{doc_name}")
            continue
        actual = _sha256_file(doc_path)
        if actual != expected:
            problems.append(
                f"契约 sha 漂移：{doc_name} 期望 {str(expected)[:16]}… 实际 {actual[:16]}…"
            )
    return problems


def verify_contract_binding(name: str) -> list[str]:
    """装载并按名绑定；返回问题列表（空 = 通过）。"""
    return contract_binding_problems(load_schema(name))


def verify_all_bindings() -> dict[str, list[str]]:
    """对全部 schema 做绑定检查（审计/测试入口）。"""
    out: dict[str, list[str]] = {}
    for name in sorted(SCHEMA_FILES):
        try:
            out[name] = verify_contract_binding(name)
        except GraphError as exc:
            out[name] = [f"{exc.code}: {exc.message}"]
    return out


def assert_contract_bindings() -> None:
    """绑定不成立 ⇒ 抛 ``GRAPH_INTERNAL``（B1 起在读写前调用）。"""
    problems = verify_all_bindings()
    bad = {k: v for k, v in problems.items() if v}
    if bad:
        raise GraphError(GRAPH_INTERNAL, "契约 sha 绑定失败", detail={"problems": bad})


# ── 最小 JSON Schema 子集校验器 ────────────────────────────────────────────


def _type_ok(instance: object, expected: str) -> bool:
    if expected == "null":
        return instance is None
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "integer":
        # 注意：Python 里 bool 是 int 子类，必须排除，否则 True 会被当整数放过。
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "object":
        return isinstance(instance, dict)
    return False


def _resolve_ref(ref: object, root: dict) -> dict:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise GraphError(GRAPH_INTERNAL, f"不支持的 $ref（仅本地 #/...）：{ref!r}")
    node: object = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise GraphError(GRAPH_INTERNAL, f"$ref 无法解析：{ref!r}")
        node = node[part]
    if not isinstance(node, dict):
        raise GraphError(GRAPH_INTERNAL, f"$ref 目标不是对象：{ref!r}")
    return node


def _check_unsupported(schema: dict, path: str, code: str,
                       errors: list[ValidationError]) -> bool:
    """schema 里出现不支持的关键字 ⇒ 记一条错误并返回 False（fail-closed）。"""
    unknown = sorted(set(schema) - SUPPORTED_KEYWORDS - ANNOTATION_KEYWORDS)
    if not unknown:
        return True
    errors.append(ValidationError(
        path=path,
        message=f"schema 含校验器不支持的关键字 {unknown}（fail-closed，不跳过）",
        code=code,
    ))
    return False


def _validate(instance: object, schema: dict, path: str, root: dict,
              code: str, errors: list[ValidationError]) -> None:
    if not isinstance(schema, dict):
        errors.append(ValidationError(path, "schema 节点必须是对象", code))
        return
    if not _check_unsupported(schema, path, code, errors):
        return

    # $ref：解析后递归（不做环检测 —— 契约 schema 无环，若出现环会深度递归暴露）
    if "$ref" in schema:
        _validate(instance, _resolve_ref(schema["$ref"], root), path, root, code, errors)
        return

    # type
    if "type" in schema:
        expected = schema["type"]
        types = [expected] if isinstance(expected, str) else list(expected)
        if not any(_type_ok(instance, t) for t in types):
            errors.append(ValidationError(
                path, f"类型应为 {types}，实际 {type(instance).__name__}", code))
            return  # 类型不符则后续关键字无意义

    # const / enum
    if "const" in schema and instance != schema["const"]:
        errors.append(ValidationError(path, f"应等于 {schema['const']!r}", code))
    if "enum" in schema:
        allowed = schema["enum"]
        if isinstance(allowed, list) and instance not in allowed:
            errors.append(ValidationError(path, f"应为 {allowed} 之一，实际 {instance!r}", code))

    # oneOf / anyOf / allOf / not
    if isinstance(schema.get("oneOf"), list):
        hits = 0
        for sub in schema["oneOf"]:
            probe: list[ValidationError] = []
            _validate(instance, sub, path, root, code, probe)
            if not probe:
                hits += 1
        if hits != 1:
            errors.append(ValidationError(path, f"oneOf 应恰好命中 1 个分支，实际 {hits}", code))
    if isinstance(schema.get("anyOf"), list):
        ok_any = False
        for sub in schema["anyOf"]:
            probe = []
            _validate(instance, sub, path, root, code, probe)
            if not probe:
                ok_any = True
                break
        if not ok_any:
            errors.append(ValidationError(path, "anyOf 未命中任何分支", code))
    if isinstance(schema.get("allOf"), list):
        for sub in schema["allOf"]:
            _validate(instance, sub, path, root, code, errors)
    if "not" in schema:
        probe = []
        _validate(instance, schema["not"], path, root, code, probe)
        if not probe:
            errors.append(ValidationError(path, "not 分支不应命中", code))

    # string
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(ValidationError(
                path, f"长度应 ≥{schema['minLength']}，实际 {len(instance)}", code))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(ValidationError(
                path, f"长度应 ≤{schema['maxLength']}，实际 {len(instance)}", code))
        if isinstance(schema.get("pattern"), str):
            if re.search(schema["pattern"], instance) is None:
                errors.append(ValidationError(
                    path, f"应匹配 {schema['pattern']!r}，实际 {instance!r}", code))

    # number / integer
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(ValidationError(path, f"应 ≥{schema['minimum']}，实际 {instance}", code))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(ValidationError(path, f"应 ≤{schema['maximum']}，实际 {instance}", code))

    # array
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(ValidationError(
                path, f"元素数应 ≥{schema['minItems']}，实际 {len(instance)}", code))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(ValidationError(
                path, f"元素数应 ≤{schema['maxItems']}，实际 {len(instance)}", code))
        items = schema.get("items")
        if isinstance(items, dict):
            for i, item in enumerate(instance):
                _validate(item, items, f"{path}[{i}]", root, code, errors)

    # object
    if isinstance(instance, dict):
        for key in schema.get("required") or []:
            if key not in instance:
                errors.append(ValidationError(path, f"缺必填字段 {key!r}", code))
        props = schema.get("properties")
        props = props if isinstance(props, dict) else {}
        for key, sub in props.items():
            if key in instance:
                _validate(instance[key], sub, f"{path}.{key}", root, code, errors)
        extra = schema.get("additionalProperties", True)
        if extra is False:
            unknown = sorted(set(instance) - set(props))
            if unknown:
                errors.append(ValidationError(
                    path, f"不允许的额外字段 {unknown}（additionalProperties=false）", code))
        elif isinstance(extra, dict):
            for key in sorted(set(instance) - set(props)):
                _validate(instance[key], extra, f"{path}.{key}", root, code, errors)


def validate(instance: object, schema_name: str) -> ValidationResult:
    """按名校验实例。**不抛**领域错误：schema/绑定层面的问题才抛 ``GraphError``。"""
    schema = load_schema(schema_name)
    problems = contract_binding_problems(schema)
    if problems:
        raise GraphError(GRAPH_INTERNAL, "契约 sha 绑定失败",
                         detail={"schema_name": schema_name, "problems": problems})
    code = schema_failure_code(schema)
    errors: list[ValidationError] = []
    _validate(instance, schema, "$", schema, code, errors)
    return ValidationResult(ok=not errors, schema_name=schema_name, errors=errors)


def validate_or_raise(instance: object, schema_name: str) -> None:
    """校验失败 ⇒ 抛 ``GraphError``（码取 schema 的 x-failure-code）。"""
    result = validate(instance, schema_name)
    if result.ok:
        return
    first = result.errors[0]
    raise GraphError(
        first.code,
        f"{schema_name} 校验失败：{first.path} {first.message}",
        detail={"schema_name": schema_name,
                "errors": [e.to_dict() for e in result.errors]},
    )
