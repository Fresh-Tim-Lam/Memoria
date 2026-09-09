SIDECAR_SUFFIX = ".memoria.yaml"
SIDECAR_SCHEMA_VERSION = 1

MEMORIA_DIR = ".memoria"
SIDECARS_DIR = "sidecars"
MANIFEST_FILENAME = "manifest.yaml"
# pending 提议持久化：当前格式 JSON（YAML 全量解析/转储太慢，见 scripts/benchmark/maintenance/trace_kp_confirm.py）
PENDING_FILENAME = "pending.json"
PENDING_LEGACY_YAML_FILENAME = "pending.yaml"

SKIP_DIR_NAMES = frozenset({
    ".memoria",
    ".git",
    ".build",
    "__pycache__",
    "node_modules",
})
