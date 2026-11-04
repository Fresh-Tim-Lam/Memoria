"""多层次图谱 multilevel 包（0.5 · B1 起）。

B1 交付：I-01 DataSourceReader / I-12 ErrorMap / I-13 SchemaValidator。
事实只读；禁止写 sidecar（D-3）。
"""
from memoria.graph.multilevel.datasource import (
    E_RELATION_MIN,
    DataSource,
    DataSourceReader,
    read_only_guard,
    snapshot_kb,
)
from memoria.graph.multilevel.errors import (
    ERROR_SPECS,
    GRAPH_INTERNAL,
    GraphError,
    canonicalize,
    spec_for,
)
from memoria.graph.multilevel.schema import (
    SCHEMA_FILES,
    validate,
    validate_or_raise,
    verify_all_bindings,
)

__all__ = [
    "E_RELATION_MIN",
    "DataSource",
    "DataSourceReader",
    "read_only_guard",
    "snapshot_kb",
    "ERROR_SPECS",
    "GRAPH_INTERNAL",
    "GraphError",
    "canonicalize",
    "spec_for",
    "SCHEMA_FILES",
    "validate",
    "validate_or_raise",
    "verify_all_bindings",
]
