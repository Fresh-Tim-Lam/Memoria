"""多层次图谱 multilevel 包（0.5）。

- **B1**：I-01 ``DataSourceReader`` / I-12 ``ErrorMap`` / I-13 ``SchemaValidator``；
- **B2**：I-02 ``GraphViewBuilder`` / I-03 ``RegistryService`` / I-04 ``ClusterRunBuilder``。

事实只读；禁止写 sidecar（D-3）；簇/run/视图全为**派生**，不是事实源。
"""
from memoria.graph.multilevel.cluster_run import (
    RUN_STATUSES,
    ClusterRun,
    ClusterRunBuilder,
    adopt_run,
    build_run_id,
    cluster_key,
    params_hash,
    request_candidate_run,
    select_semantic_edges,
)
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
from memoria.graph.multilevel.graph_view import (
    DATA_STATES,
    GraphView,
    GraphViewBuilder,
    ViewFamily,
    validate_level_view,
)
from memoria.graph.multilevel.registry import (
    DIM_KINDS,
    DIM_STATUSES,
    RegistryService,
    make_dimension,
    validate_registry,
    verify_history_chain,
)
from memoria.graph.multilevel.schema import (
    SCHEMA_FILES,
    validate,
    validate_or_raise,
    verify_all_bindings,
)

__all__ = [
    # B1
    "E_RELATION_MIN", "DataSource", "DataSourceReader", "read_only_guard", "snapshot_kb",
    "ERROR_SPECS", "GRAPH_INTERNAL", "GraphError", "canonicalize", "spec_for",
    "SCHEMA_FILES", "validate", "validate_or_raise", "verify_all_bindings",
    # B2
    "GraphView", "GraphViewBuilder", "ViewFamily", "validate_level_view", "DATA_STATES",
    "RegistryService", "make_dimension", "validate_registry", "verify_history_chain",
    "DIM_KINDS", "DIM_STATUSES",
    "ClusterRun", "ClusterRunBuilder", "RUN_STATUSES", "build_run_id", "params_hash",
    "cluster_key", "select_semantic_edges", "request_candidate_run", "adopt_run",
]
