SIDECAR_SUFFIX = ".memoria.yaml"
SIDECAR_SCHEMA_VERSION = 1

MEMORIA_DIR = ".memoria"
SIDECARS_DIR = "sidecars"
MANIFEST_FILENAME = "manifest.yaml"
PENDING_FILENAME = "pending.yaml"

SKIP_DIR_NAMES = frozenset({
    ".memoria",
    ".git",
    ".build",
    "__pycache__",
    "node_modules",
})
