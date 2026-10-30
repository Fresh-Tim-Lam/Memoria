# task-246 S2 更正清单（dispatch-log done 行的 report 更正目标）

> **用途**：`team/dispatch-log.jsonl` 中 8 条历史 `done` 行引用的产物在 **Memoria 工作区**不存在；
> 经核实，产物真实存在于 **DSH 仓**（`D:\deepseek-harness`）的对应相对路径。按 append-only 更正协议
> （`scripts/agent/dispatch_log.py` 文档「更正协议」），**不改历史行**，追加 `phase=backfill` + `corrects`
> 记录把 `report` 更正为本文件（可验证存在的更正目标），并在下表留下逐条结论。
>
> **本文件是更正目标，不是"已修复"声明**：它记录的是"原声称的产物在 Memoria 工作区不存在、实际位于外部仓"这一事实。
> 生成时间：2026-10-30；执行：steward（task-246）。

## 逐条结论

| dispatch-log 行 | 时间(UTC) | actor / task | 原 report（Memoria 相对路径） | 实际位置（DSH 仓） | sha256 | 大小 | 类型 | 结论 |
|---|---|---|---|---|---|---|---|---|
| 766 | 2026-10-29T12:48:43Z | panel-graph-fixer / task-232 | `artifacts/agent/panel-ui/browser-check/fixer-232.png` | `D:\deepseek-harness\artifacts\agent\panel-ui\browser-check\fixer-232.png` | `ffc1b05ce82c0a99bb8d6243cb2bec2ab8f6b8ceb14d85a86bfb7cfcb9e32f7f` | 159345 | PNG 截图 | **跨仓路径迁移**：产物在 DSH 仓；Memoria 侧仅有相对路径记录 ⇒ 按更正协议指向本清单 |
| 771 | 2026-10-29T13:19:24Z | panel-graph-fixer / task-237 | `artifacts/agent/panel-ui/browser-check/hub-237.png` | `D:\deepseek-harness\artifacts\agent\panel-ui\browser-check\hub-237.png` | `12c5fb945f3b3b6a78b29155b8300a9f393090e86dde9e55091df8a4c5438ffa` | 100431 | PNG 截图 | 同上 |
| 774 | 2026-10-29T13:34:29Z | panel-graph-fixer / task-236 | `artifacts/agent/panel-ui/browser-check/236-tier-a.png` | `D:\deepseek-harness\artifacts\agent\panel-ui\browser-check\236-tier-a.png` | `6c00e0b9c36a84705d51d9486e8cfecfdf42167147b99faf0862136eaddb9e85` | 50890 | PNG 截图 | 同上 |
| 777 | 2026-10-29T13:52:56Z | panel-graph-fixer / task-234 | `packages/experimental/client-ui-agent-team/src/client/panel/engine/layout.ts` | `D:\deepseek-harness\packages\experimental\client-ui-agent-team\src\client\panel\engine\layout.ts` | `49787f4268f2eecf34207ca41ad1a66a0539139739b1d3cf5991b8184c666d3b` | 11495 | 源码文件 | **跨仓源码引用**：该路径是 DSH 仓相对路径，不是 Memoria 工作区路径；实际文件在 DSH 仓存在 ⇒ 指向本清单 |
| 787 | 2026-10-29T15:03:28Z | panel-graph-fixer / task-239 | `artifacts/agent/panel-ui/browser-check/239-interaction.json` | `D:\deepseek-harness\artifacts\agent\panel-ui\browser-check\239-interaction.json` | `94885e7f2e5c76dfdf9f5caad04b74cffbf4d20c3f5474fa5b30fd7a558a07db` | 1190 | JSON 指标 | 同上（跨仓路径迁移） |
| 795 | 2026-10-29T19:01:51Z | panel-graph-fixer / task-240 | `artifacts/agent/panel-ui/browser-check/240-assertions.json` | `D:\deepseek-harness\artifacts\agent\panel-ui\browser-check\240-assertions.json` | `e4e86420a909518baa1141c7d14eccebe5cdcae95958cf33f3c72802f8422f3a` | 2546 | JSON 断言 | 同上 |
| 798 | 2026-10-29T19:16:01Z | panel-graph-fixer / task-241 | `artifacts/agent/panel-ui/browser-check/241-assertions.json` | `D:\deepseek-harness\artifacts\agent\panel-ui\browser-check\241-assertions.json` | `461de566fcd66f52200a759f0b3c95b9f5915d5979498c44a8943645d9622cf8` | 2435 | JSON 断言 | 同上 |
| 831 | 2026-10-30T03:10:39Z | panel-graph-fixer / task-244 | `artifacts/agent/panel-ui/browser-check/244-assertions.json` | `D:\deepseek-harness\artifacts\agent\panel-ui\browser-check\244-assertions.json` | `527c30845d4c627ef903846c252d081efb6726e328332eb81a6aff5020071266` | 1326 | JSON 断言 | 同上（task-246 建票后新增的第 8 条） |

> 全部 8 条均为「文件在 DSH 仓存在、但 dispatch-log 记的是 Memoria 相对路径」的情况；
> 无一条是「产物本就不存在」。sha256 为 2026-10-30 复核时读取的当前字节（外部仓文件若后续被改，hash 会变，应以 DSH 仓 git 历史为准）。

## 更正方式（已执行）

对上述 8 行各追加一条 `phase=backfill` 记录：
`corrects={line: <行号>, field: "report", old: <原路径>, new: "team/steward/task-246-s2-cleanup.md"}`。
`team_audit.py::silent_failure` 会验证 `corrects.new` 指向的文件真实存在（本文件）。

## 为什么不是"回填历史"

- 未修改 dispatch-log 任何旧行（append-only）；
- 本文件只记录"原路径在 Memoria 不存在、实际在 DSH 仓"的事实，不声称原 done 的 Memoria 产物已验证；
- 若要真正在 Memoria 侧复核这些证据，需要把 DSH 仓对应截图/断言复制进 `artifacts/agent/panel-ui/browser-check/`
  （属后续可选动作，不在本票强制范围；复制后可在本表更新说明，但历史行仍不改）。
