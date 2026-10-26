"""Phase 4 增补 D-KGV-15/16（D-KGV-14 已应用，幂等跳过）。"""
import io
import sys

P = "docs/design/kg-visualization-v0.md"
r = io.open(P, encoding="utf-8", newline="").read()


def apply(old, new, marker, label):
    """幂等：marker 已存在则跳过；否则 old 必须命中。"""
    global r
    if marker in r:
        print("  SKIP（已应用）", label)
        return
    if old not in r:
        sys.exit("ABORT: 未命中 " + label)
    r = r.replace(old, new, 1)
    print("  OK", label)


# ── D-KGV-15：T-double 澄清 ────────────────────────────────────
apply(
    "| **T-double** | 同一节点同时用颜色+大小编码 degree ⇒ 检查双重编码冲突 | 有冲突 ⇒ 二选一 |",
    "| **T-double** | 【澄清后】检查两视觉通道是否编码**不同变量**或**方向相反**；同变量冗余编码（颜色与大小都编码 degree 且方向一致）⇒ **不视为冲突**（强化而非矛盾） | 有真冲突 ⇒ 二选一 |",
    "同变量冗余编码（颜色与大小都编码 degree",
    "D-KGV-15 T-double 表格行",
)

apply(
    "> ★ **T-size-3 是\"连续 vs 分桶\"的直接证据**：若实现里其实偷偷按档位取整，",
    "> **D-KGV-15（T-double 澄清）**：galaxy 风格同时用颜色与大小编码 degree ⇒\n"
    "> 这是**同变量冗余编码**，判定为**允许**（冗余强化 ≠ 冲突）。\n"
    "> 真正的冲突是：颜色编码 A 变量、大小编码 B 变量，或两者方向相反。\n"
    "> T-double 的实现应检查后者，不应对前者报错。\n"
    "\n"
    "> ★ **T-size-3 是\"连续 vs 分桶\"的直接证据**：若实现里其实偷偷按档位取整，",
    "D-KGV-15（T-double 澄清）",
    "D-KGV-15 说明段",
)

# ── D-KGV-16：3D 光晕等大 ─────────────────────────────────────
apply(
    "**falsifier**：若 3D 深度判读任务正确率 ≥80% 且归一组显著优于等大组 ⇒ 可撤回。",
    """**falsifier**：若 3D 深度判读任务正确率 ≥80% 且归一组显著优于等大组 ⇒ 可撤回。

### D-KGV-16 · 3D 光晕（galaxy halo）也必须等大

```
发现：节点 mesh 已 scale=1（等大），但 galaxy 的 halo（装饰性发光）仍随 degree 变
⇒ 光晕是【表观的尺寸线索】⇒ 若随 degree 变，等于绕过"3D 不做大小编码"的裁决
⇒ 裁决：3D 光晕半径【不随 degree 变化】（统一值，或仅随 zoom 变化）
```

**理由**：D-KGV-04 的裁决依据是"3D 里尺寸通道不可解释（透视 1.78× 混淆）"。
如果 mesh 等大但光晕随度数变大，用户在 3D 里**仍然看到"度数大的看起来更大"** ⇒
该裁决被装饰层绕过。判据必须是【用户在 3D 里是否感知到尺寸差异】，而不是 `mesh.scale === 1`。""",
    "D-KGV-16 · 3D 光晕",
    "D-KGV-16 3D光晕",
)

io.open(P, "w", encoding="utf-8", newline="").write(r)
print("  设计文档更新完成：%d 字节" % len(r))
