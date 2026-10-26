"""发布包格式与完整性校验（task-181 · 不含数字签名）。

## 人要求（缩小范围后的最终版本）

> 「算了不管了，给厕所上锁，**保证发布包格式**就好了」

⇒ 本模块只做**格式 + 完整性**：
- 发布时：门禁拒绝**结构不对 / 缺文件 / 多文件 / zip 结构异常**的包；
- 客户端：可复用的 `verify_package()` 校验下载到的包是否完整。

## ⚠️ 诚实边界（**必读，不要在文档/UI 里夸大成"防篡改"**）

**本方案保护**：
- 发布时格式错误、打包缺文件、多余文件（夹带）
- zip 结构异常（重复条目 / 路径穿越 / EOCD 尾随数据）
- 传输损坏、下载不完整

**本方案不保护**：
- **有意篡改** —— 攻击者可以替换包内文件**并重算 manifest 里的哈希**。
  没有数字签名，客户端**察觉不到**这种替换。

⇒ 正确表述：**「已校验包结构与完整性（不含数字签名）」**
❌ 禁止表述：「防篡改」「安全」「已签名」

## 规范化字节为什么还要写死

**目的不是签名，而是可复现/可 diff/可复核**：同一份内容在任何机器上算出同一串字节，
这样两个人各自生成 manifest 可以直接 `diff`，review 时能看到真实差异
（而不是被键序/空格/换行差异淹没）。
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal

MANIFEST_SCHEMA = "memoria-release-manifest/v1"
MANIFEST_NAME = "release-manifest.json"

#: 发布包**顶层必须**存在的条目（目录以 `/` 结尾）。
REQUIRED_TOP_LEVEL: tuple[str, ...] = (
    "Memoria.exe",
    "VERSION",
    "manifest.json",
    "lib/",
    "resources/",
    "config/",
    "hf/",
)

#: 允许存在但不是必须的顶层条目。
OPTIONAL_TOP_LEVEL: tuple[str, ...] = (
    "README.txt",
    "Memoria.exe.config",
    MANIFEST_NAME,
)

#: **禁止**随包的顶层条目（运行时残留 / 缓存 / 版本控制 / 诊断日志）。
#:
#: 依据：在真实 `Package/` 上跑门禁（2026-10-26）抓到这三类非预期条目 ——
#:   · `.gitkeep`：占位文件，不应进分发包；
#:   · `frameless-ok.txt` / `window-diag.txt`：**运行时诊断日志**，
#:     内含本机绝对路径与窗口坐标 ⇒ 既无用途，又泄露维护者环境信息。
#: ⇒ 全部列为禁止项，而**不是**放宽"预期集合"去容纳它们（那等于把残留合法化）。
FORBIDDEN_TOP_LEVEL: tuple[str, ...] = (
    "logs/",
    "cache/",
    ".git/",
    "__pycache__/",
    ".gitkeep",
    "frameless-ok.txt",
    "window-diag.txt",
)

#: 计算哈希时跳过的顶层目录（运行动态产物，不属于"包内容"）。
HASH_SKIP_TOP_LEVEL: tuple[str, ...] = ("logs", "cache", "__pycache__")

#: 计算哈希时跳过的顶层文件 —— 清单自身不能进自己的清单（自引用悖论）。
HASH_SKIP_TOP_FILES: tuple[str, ...] = (MANIFEST_NAME,)


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """规范化字节：**键排序 + 无空格 + 单个结尾 LF + UTF-8**。

    ## 用途是"可复现/可 diff"，不是"可签名"

    同一份内容在任何平台算出同一串字节 ⇒ 两个人生成的 manifest 能直接 `diff`，
    review 看到的是真实差异（不是键序/空格/CRLF 噪声）。
    """
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class CheckResult:
    """校验结果。`ok=False` 时 `failures` 必非空。"""

    ok: bool
    failures: list[str] = field(default_factory=list)

    @classmethod
    def pass_(cls) -> "CheckResult":
        return cls(ok=True, failures=[])

    @classmethod
    def fail(cls, *items: str) -> "CheckResult":
        return cls(ok=False, failures=[i for i in items if i])

    def extend(self, other: "CheckResult") -> "CheckResult":
        if other.ok:
            return self
        self.ok = False
        self.failures.extend(other.failures)
        return self


def rel_posix(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _iter_package_files(package_root: Path) -> Iterable[Path]:
    """遍历包内应被哈希的文件（跳过运行时目录 + 清单自身）。"""
    for path in sorted(package_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(package_root)
        if rel.parts and rel.parts[0] in HASH_SKIP_TOP_LEVEL:
            continue
        if len(rel.parts) == 1 and rel.parts[0] in HASH_SKIP_TOP_FILES:
            continue
        yield path


def build_manifest(
    *,
    package_root: Path,
    version: str,
    asset_name: str,
    asset_bytes: int = 0,
    asset_path: Path | None = None,
    built_at: str | None = None,
) -> dict[str, Any]:
    """扫描包目录生成完整性清单。"""
    files = []
    for path in _iter_package_files(package_root):
        files.append(
            {
                "path": rel_posix(path, package_root),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )

    asset: dict[str, Any] = {"name": asset_name, "bytes": asset_bytes}
    if asset_path is not None and asset_path.is_file():
        asset["bytes"] = asset_path.stat().st_size
        asset["sha256"] = sha256_file(asset_path)

    return {
        "schema": MANIFEST_SCHEMA,
        "format_version": 1,
        "version": version,
        "built_at": built_at or datetime.now(timezone.utc).isoformat(),
        "asset": asset,
        "layout": {
            "required": list(REQUIRED_TOP_LEVEL),
            "optional": list(OPTIONAL_TOP_LEVEL),
            "forbidden": list(FORBIDDEN_TOP_LEVEL),
        },
        "files": files,
    }


# ── A. 结构校验 ────────────────────────────────────────────────────────────


def verify_layout(*, package_root: Path, manifest: dict[str, Any] | None = None) -> CheckResult:
    """顶层必须恰好是 required ∪ optional；必含齐全；禁止条目不得存在。"""
    failures: list[str] = []
    present: set[str] = set()
    for child in package_root.iterdir():
        present.add(child.name + "/" if child.is_dir() else child.name)

    required, optional, forbidden = (
        set(REQUIRED_TOP_LEVEL),
        set(OPTIONAL_TOP_LEVEL),
        set(FORBIDDEN_TOP_LEVEL),
    )

    missing = sorted(required - present)
    if missing:
        failures.append(f"缺少必含顶层条目：{missing}")

    bad = sorted(present & forbidden)
    if bad:
        failures.append(f"包含禁止的顶层条目：{bad}")

    unexpected = sorted(present - required - optional - forbidden)
    if unexpected:
        failures.append(f"存在未声明的顶层条目：{unexpected}")

    if manifest is not None:
        declared = set((manifest.get("layout") or {}).get("required") or [])
        if declared and declared != required:
            failures.append(
                f"manifest.layout.required 与代码契约不一致："
                f"声明={sorted(declared)} 契约={sorted(required)}"
            )

    return CheckResult.pass_() if not failures else CheckResult.fail(*failures)


# ── B. 双向文件校验 ────────────────────────────────────────────────────────


def verify_readback(*, package_root: Path, manifest: dict[str, Any]) -> CheckResult:
    """双向：清单声明的都在且哈希一致；实际文件都在清单里（无夹带）。"""
    failures: list[str] = []
    declared: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("files") or []:
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            failures.append(f"清单条目缺少 path：{entry!r}")
            continue
        declared[path] = entry

    for path, entry in declared.items():
        actual = package_root / path
        if not actual.is_file():
            failures.append(f"清单声明的文件在包中不存在：{path}")
            continue
        actual_sha = sha256_file(actual)
        if actual_sha != entry.get("sha256"):
            failures.append(
                f"sha256 不匹配：{path} 声明={entry.get('sha256')} 实际={actual_sha}"
            )
        actual_bytes = actual.stat().st_size
        if entry.get("bytes") is not None and actual_bytes != entry["bytes"]:
            failures.append(f"大小不匹配：{path} 声明={entry['bytes']} 实际={actual_bytes}")

    for path in _iter_package_files(package_root):
        rel = rel_posix(path, package_root)
        if rel not in declared:
            failures.append(f"包中存在未在清单声明的文件：{rel}")

    return CheckResult.pass_() if not failures else CheckResult.fail(*failures)


# ── C. 版本一致性 ──────────────────────────────────────────────────────────


def verify_versions(
    *, package_root: Path, manifest: dict[str, Any], expected_version: str = ""
) -> CheckResult:
    """`VERSION` == `manifest.version` == 期望版本（release 标题版本）。"""
    failures: list[str] = []
    version_file = package_root / "VERSION"
    # `utf-8-sig`：VERSION 常由构建脚本写，Windows 的 `Set-Content -Encoding UTF8` 带 BOM；
    # 用 `utf-8` 读会把 `\ufeff` 留在串首 ⇒ 假报版本不一致（实测踩到）。
    file_version = (
        version_file.read_text(encoding="utf-8-sig").strip() if version_file.is_file() else None
    )
    manifest_version = manifest.get("version")

    if file_version is None:
        failures.append("包中缺少 VERSION 文件")
    elif file_version != manifest_version:
        failures.append(f"VERSION({file_version!r}) 与 manifest.version({manifest_version!r}) 不一致")

    if expected_version and manifest_version != expected_version:
        failures.append(
            f"manifest.version({manifest_version!r}) 与期望版本({expected_version!r}) 不一致"
        )

    pkg_manifest = package_root / "manifest.json"
    if pkg_manifest.is_file():
        try:
            data = json.loads(pkg_manifest.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and data.get("version") not in (None, manifest_version):
                failures.append(
                    f"Package/manifest.json.version({data.get('version')!r}) "
                    f"与 release-manifest.version({manifest_version!r}) 不一致"
                )
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"Package/manifest.json 无法解析：{exc}")

    return CheckResult.pass_() if not failures else CheckResult.fail(*failures)


# ── D. zip 卫生 ────────────────────────────────────────────────────────────

#: zip 结构末段签名（End of Central Directory）
_EOCD_SIG = b"PK\x05\x06"


def _has_trailing_data_after_eocd(zip_path: Path) -> bool:
    """zip 末尾 EOCD 之后是否有尾随数据（常见于"在 zip 后追加内容"的攻击/损坏）。

    EOCD 结构：`PK\x05\x06` + 18 字节固定字段 + 注释长度 2 字节 + 注释。
    ⇒ 合法的 zip 长度 = EOCD 起始 + 22 + 注释长度。
    """
    data = zip_path.read_bytes()
    idx = data.rfind(_EOCD_SIG)
    if idx < 0:
        return False  # 没有 EOCD ⇒ 交给 zipfile 报"不是 zip"
    if idx + 22 > len(data):
        return True  # EOCD 本身不完整
    comment_len = int.from_bytes(data[idx + 20 : idx + 22], "little")
    expected_end = idx + 22 + comment_len
    return len(data) != expected_end


def _is_unsafe_zip_name(name: str) -> bool:
    """路径穿越 / 绝对路径 / 反斜杠变体 ⇒ 不安全。"""
    if name.startswith("/") or name.startswith("\\"):
        return True
    if ".." in Path(name.replace("\\", "/")).parts:
        return True
    # Windows 盘符绝对路径（C:...）
    if len(name) >= 2 and name[1] == ":":
        return True
    return False


def verify_zip(*, zip_path: Path, manifest: dict[str, Any]) -> CheckResult:
    """zip 卫生：重复条目 / 路径穿越 / 条目集合与清单一致 / 无 EOCD 尾随。"""
    failures: list[str] = []

    if _has_trailing_data_after_eocd(zip_path):
        failures.append("zip 末尾存在 EOCD 之后的尾随数据（可能被追加内容或传输损坏）")

    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = [i.filename for i in zf.infolist() if not i.is_dir()]

            seen: set[str] = set()
            dupes = []
            for name in names:
                if name in seen:
                    dupes.append(name)
                seen.add(name)
            if dupes:
                failures.append(f"zip 存在同名重复条目：{sorted(set(dupes))}")

            unsafe = sorted({n for n in names if _is_unsafe_zip_name(n)})
            if unsafe:
                failures.append(f"zip 存在不安全路径（路径穿越/绝对路径）：{unsafe}")

            declared = {e.get("path") for e in (manifest.get("files") or []) if e.get("path")}
            actual = set(names)
            # 清单自身不能进自己的清单（自引用悖论）⇒ 它在包内属"允许但未声明"。
            # 不排除的话，用真实打包工具把 Package/ 整个压成 zip 后必然误报
            # "未在清单声明的条目：release-manifest.json"（实测踩到）。
            actual_for_compare = actual - set(HASH_SKIP_TOP_FILES)
            extra = sorted(actual_for_compare - declared)
            if extra:
                failures.append(f"zip 中存在未在清单声明的条目：{extra}")
            # 反向：清单声明的必须在 zip 里（这里用未过滤的 actual）
            missing = sorted(declared - actual)
            if missing:
                failures.append(f"zip 中缺少清单声明的条目：{missing}")
    except zipfile.BadZipFile as exc:
        # 常见触发：zip 被追加/截断后局部文件头与中央目录不一致（T-fmt-10 的落点）。
        # 原文对用户不友好，补一句可操作说明。
        failures.append(
            f"zip 结构损坏或已被改写（局部文件头与中央目录不一致）：{exc}"
            " ⇒ 该文件不是发布时打出的那一份，请重新下载"
        )

    return CheckResult.pass_() if not failures else CheckResult.fail(*failures)


# ── 客户端可复用：统一入口 ─────────────────────────────────────────────────


def verify_package(
    path: str | Path,
    manifest: dict[str, Any],
    *,
    expected_version: str = "",
    check_asset_bytes: bool = False,
) -> CheckResult:
    """**客户端可复用的统一校验入口**（供 task-180 更新机制调用）。

    `path` 可以是：
    - **目录**（已解压的 Package）⇒ 走 A 结构 + B 双向 + C 版本
    - **zip 文件** ⇒ 额外走 D zip 卫生（含条目集合与清单一致）+ 逐条目内容哈希

    ## `check_asset_bytes` 的语义（**不要写反**）

    它控制是否校验"**这一个 zip 文件本身的** sha256/bytes"（`manifest.asset`）。

    | 场景 | 该传什么 | 理由 |
    |---|---|---|
    | **发布门禁**（校验即将发布的那一个 zip） | `True` | 就是要钉住"发出去的正是这个文件" |
    | **客户端校验下载的包** | `True` | 下载到的就该是清单登记的那个资产（传输完整性） |
    | **只校验内容、容忍重新打包** | `False` | 内容相同但重新压缩 ⇒ 字节必然不同，不该因此失败（T-fmt-4） |

    ⚠️ 注意：`asset.sha256` 绑的是**打包后的字节**。若换了压缩级别/工具重打包，
    内容不变但字节变了 ⇒ `check_asset_bytes=True` 会失败。这是**预期行为**，
    因为发布门禁必须钉住确切的那份资产。

    ## 不做的事（诚实边界）

    **不做数字签名验证** —— 本方案没有签名。
    因此本函数**无法察觉**"攻击者替换文件并重算清单哈希"这类有意篡改。
    它能抓的是：格式错、缺文件、多文件、zip 结构异常、传输损坏、下载不完整。
    """
    target = Path(path)
    result = CheckResult.pass_()

    if target.is_file():
        # zip 形态：结构卫生 + 逐条目内容哈希
        result.extend(verify_zip(zip_path=target, manifest=manifest))
        result.extend(_verify_zip_content_hashes(zip_path=target, manifest=manifest))

        if check_asset_bytes:
            asset = manifest.get("asset") or {}
            actual_size = target.stat().st_size
            if asset.get("bytes") and asset["bytes"] != actual_size:
                result.ok = False
                result.failures.append(
                    f"资产大小不符：清单={asset['bytes']} 实际={actual_size}"
                )
            if asset.get("sha256"):
                actual_sha = sha256_file(target)
                if actual_sha != asset["sha256"]:
                    result.ok = False
                    result.failures.append(
                        f"资产 sha256 不符：清单={asset['sha256']} 实际={actual_sha}"
                    )
        return result

    if target.is_dir():
        result.extend(verify_layout(package_root=target, manifest=manifest))
        result.extend(verify_readback(package_root=target, manifest=manifest))
        if manifest.get("version"):
            result.extend(
                verify_versions(
                    package_root=target, manifest=manifest, expected_version=expected_version
                )
            )
        return result

    return CheckResult.fail(f"路径不存在：{target}")


def _verify_zip_content_hashes(*, zip_path: Path, manifest: dict[str, Any]) -> CheckResult:
    """对 zip **条目内容**逐个算 sha256，与清单比对（不解压到磁盘）。"""
    failures: list[str] = []
    declared = {e["path"]: e for e in (manifest.get("files") or []) if e.get("path")}
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for path, entry in declared.items():
                try:
                    data = zf.read(path)
                except KeyError:
                    failures.append(f"zip 中缺少清单声明的条目：{path}")
                    continue
                actual_sha = hashlib.sha256(data).hexdigest()
                if actual_sha != entry.get("sha256"):
                    failures.append(
                        f"zip 条目 sha256 不匹配：{path} 声明={entry.get('sha256')} 实际={actual_sha}"
                    )
                if entry.get("bytes") is not None and len(data) != entry["bytes"]:
                    failures.append(
                        f"zip 条目大小不匹配：{path} 声明={entry['bytes']} 实际={len(data)}"
                    )
    except zipfile.BadZipFile as exc:
        failures.append(
            f"zip 结构损坏或已被改写（无法读取条目内容）：{exc} ⇒ 请重新下载"
        )
    return CheckResult.pass_() if not failures else CheckResult.fail(*failures)
