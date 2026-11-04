"""多层次图谱 multilevel 包（0.5）。

- **B1**：I-01 ``DataSourceReader`` / I-12 ``ErrorMap`` / I-13 ``SchemaValidator``；
- **B2**：I-02 ``GraphViewBuilder`` / I-03 ``RegistryService`` / I-04 ``ClusterRunBuilder``；
- **B5**：I-09 ``CacheStore`` / I-10 ``AuditLog`` / I-11 ``G6Store``/``G7Store``。

事实只读；禁止写 sidecar（D-3）；簇/run/视图全为**派生**，不是事实源。
"""
from memoria.graph.multilevel.audit import AuditError, AuditLog, AuditRecord
from memoria.graph.multilevel.cache import CacheEntry, CacheError, CacheStore
from memoria.graph.multilevel.g6 import (
    G6_FIELDS,
    G7_FIELDS,
    G6Snapshot,
    G6Store,
    G7Snapshot,
    G7Store,
    SnapshotError,
)
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
from memoria.graph.multilevel.admission import (
    PRESENCE_VALUES,
    RULE_IDS,
    AdmissionResult,
    AdmissionService,
    FrameSpec,
    check_x_rule,
    make_frame_spec,
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
from memoria.graph.multilevel.view_model import (
    VM_EDGE_FIELDS,
    VM_NODE_FIELDS,
    VM_TOP_FIELDS,
    ViewModelBuilder,
    renderer_projection,
    validate_vm,
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
    # B3
    "AdmissionService", "AdmissionResult", "FrameSpec", "make_frame_spec",
    "check_x_rule", "PRESENCE_VALUES", "RULE_IDS",
    "ViewModelBuilder", "validate_vm", "renderer_projection",
    "VM_TOP_FIELDS", "VM_NODE_FIELDS", "VM_EDGE_FIELDS",
    # B5
    "CacheStore", "CacheEntry", "CacheError",
    "AuditLog", "AuditRecord", "AuditError",
    "G6Store", "G6Snapshot", "G6_FIELDS", "G7Store", "G7Snapshot", "G7_FIELDS", "SnapshotError",
]
