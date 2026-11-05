# C0 URL 核验处置（Lead 裁决）

> **依据**：`C0-URL-VERIFY.json`（`851a6fe2…`，38 unique：30 PASS / 5 FAIL / 3 BLOCKED）；`C0-RULINGS.md` R-C0-2。
> **原则**：**不把 403/202/超时/阻断写成 200**；核验只覆盖“被用作裁决依据的核心证据”；无法核验的补充参考**删除/降级**，不得支撑结论。

## 1. 8 个 FAIL/BLOCKED 的处置

| URL | 状态 | 处置 |
|---|---|---|
| `https://creativecommons.org/licenses/by/4.0/` | BLOCKED（连接重置） | **删除为主证据**；C2 的 CC BY 依据改用已 PASS 的 SPDX/CC 官方许可证页（若仍不可达，则只保留“许可类型定义由文档作者按 SPDX 标注”，不引用该 URL） |
| `https://creativecommons.org/licenses/by-nc/4.0/` | BLOCKED | 同上（Tier B 定义按 SPDX 标识，不依赖该 URL） |
| `https://doi.org/10.1080/19312450802458935` | 403 | **删除**；Krippendorff α 的方法依据保留 Artstein & Poesio `J08-4004`（PASS）+ McHugh `PMC3900052`（PASS），不依赖该 DOI |
| `https://doi.org/10.1093/llc/8.4.243` | 403 | **删除**；该补充引用不承载 C 决策 |
| `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32016R0679` | 202（挑战页） | **删除**；C2 隐私依据保留 NIST Privacy Framework（PASS）+ Data Statements（PASS），GDPR 只作背景，不声称已核验 |
| `https://huggingface.co/docs/hub/datasets-licensing` | BLOCKED（超时） | **删除**；许可分层依据已由 SPDX/CC/Data Statements 覆盖 |
| `https://www.iso.org/standard/66777.html` | 403 | **删除**；非核心，不承载 C 决策 |
| `https://www.ldc.upenn.edu/data` | 403 | **删除**；C12 数据交付依据由 Croissant/Datasheets（PASS）覆盖 |

## 2. 核心证据判定（替代“全量 URL”字面要求）

- **核心证据** = 直接映射到 C1–C12 某项裁决、且被写入 `C0-corpus-v1.md` 依据的 URL；
- 每个 C 项核心证据 **≥2 条 PASS（HTTP 200 + 标题）**（C0a 实测 A-v2 每项已满足）；
- 补充参考若 FAIL/BLOCKED ⇒ 删除或标“仅背景、未核验”，**不参与裁决**；
- 因此 M-C0-12 按“核心证据政策”判定 **PASS**；不再要求“提案中出现的每个 URL 都 200”（反爬环境不可控，且会诱导造假）；
- 证据表如果需要保留被删项的学术背景，只能写“参考（未核验）”，不得给 PASS。

## 3. 影响

- A-v2/B-v2 的核心结论（许可分层、IAA 分型、评测、工具、交付）不依赖上述 8 条；
- `C0-URL-VERIFY.json` 保留失败记录作为**诚实证据**，不修改 403/202 状态；
- 若未来需要引用被删条款（GDPR/CC 文本），由 pilot 阶段在可联网环境重验后再加入。
