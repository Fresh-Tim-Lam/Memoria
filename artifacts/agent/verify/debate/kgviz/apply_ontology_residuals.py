"""对 kg-ontology-v0.md 应用 D-KGV-10/11/12 三处残差修订（逐条断言命中，失败即中止）。"""
import io
import sys

P = "docs/design/kg-ontology-v0.md"
src = io.open(P, encoding="utf-8", newline="").read()
before = len(src)


def must(old, new, label):
    global src
    if old not in src:
        sys.exit("ABORT: 未命中 " + label)
    src = src.replace(old, new, 1)
    print("  OK", label)


# ── 残差 C：语料身份改三元组（禁止单一语料 sha）──────────────────
must(
    "语料 sha   051deb7895c86185…   文件清单 sha e12edfad…（182 文件）",
    "语料身份   ⚠️ 旧「语料 sha 051deb78…/182 文件」【已失效，禁止再用】\n"
    "           （2026-10-26 实测：该 sha 无法对应任何可从 git 复现的状态）",
    "残差C-旧sha作废",
)

must(
    "强制格式   (语料 sha, 测量源, 时间) 三元组 —— 缺一即 E1 无效",
    "强制格式   (HEAD sha, manifest_sha256, 测量时间) 三元组 —— 缺一即 E1 无效\n"
    "           ⚠️ 判「语料是否一致」看 manifest_sha256，不看 artifact_sha256（后者含时间戳）\n"
    "           ⚠️ 当前语料【不可从 git 复现】：git archive HEAD docs/example = 61 节点/154 边，\n"
    "              工作区 AAA_Vocab = 134 节点/404 边；方案1（构造可复现语料）实测不可行\n"
    "              ⇒ manifest_sha256 是唯一身份；工作区一变即永久失效且无法回滚\n"
    "              冻结值：HEAD d9341bd1（dirty）/ manifest a6866c46cab71c43… / 294 文件 / 134 节点 404 边",
    "残差C-三元组",
)

# ── 残差 A：build 是破坏性迁移，测量必须记录 build 状态 ──────────
must(
    "> **进一步推论**：若某设计依赖 454 那套边集，它与前端看到的 404 套**不是同一份数据** ——\n"
    "> 这类\"两条路径看不同世界\"的问题，与 D-KG-12 的「图谱↔agent 未打通」是同一类架构缺陷。",
    "> **进一步推论**：若某设计依赖 454 那套边集，它与前端看到的 404 套**不是同一份数据** ——\n"
    "> 这类\"两条路径看不同世界\"的问题，与 D-KG-12 的「图谱↔agent 未打通」是同一类架构缺陷。\n"
    ">\n"
    "> **⚠️ 残差 A（2026-10-26，D-KGV-10）：`kb_build` 是【破坏性迁移】，上面\"两条只读路径\"的说法低估了它**\n"
    "> ```\n"
    "> kb_build.py#L293-298  strip_known_wikilink_edge_hints 后 open(full,\"w\") 【真的写回源 md】\n"
    "> kb_build.py#L312     save_sidecar_for_md 【真的写回 sidecar】\n"
    "> 同一临时副本实测：build 前 collector 404 边 → build 后 collector 454 边\n"
    "> ⇒ 「404 vs 454」含 build 对源数据的一次性迁移副作用，不只是\"函数不同\"\n"
    "> ```\n"
    "> ⇒ **任何边/degree 测量必须记录 build 状态（pre_build / post_build + build sha）**，否则数字不可比。",
    "残差A-build副作用",
)

# ── 残差 B：99.2% 门禁永不触发 ────────────────────────────────
must(
    "negative gate 最大分组占比（99.2% 能可靠判\"没修好\"；不能当验收）",
    "negative gate 最大分组占比（【实测 >80% 触发】；不能当验收）\n"
    "              ⚠️ 残差 B（D-KGV-11）：原写「99.2%」是【过期数字】（来源：更早语料），\n"
    "                 当前可复现语料实测 HEAD 81.97% / live 89.55% ⇒ 99.2% 阈值【永远不会触发】\n"
    "                 = gate 不存在 ⇒ 已改为 80%",
    "残差B-99.2%改80%",
)

io.open(P, "w", encoding="utf-8", newline="").write(src)
print("  长度 %d -> %d" % (before, len(src)))
