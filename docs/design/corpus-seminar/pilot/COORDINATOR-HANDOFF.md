# 语料 pilot · 协调人交接单（可直接转发）

> 用途：人把本文件/下面「转发文案」发给协调人即可启动；协调人按 `HUMAN-ANNOTATION-KIT.md` 与 `human-kit/COORDINATOR-CHECKLIST.md` 执行。
> 状态：pilot 双标注，**不是 0.5 发版**；0.5 仍 HOLD。

## 一、可直接转发的文案

```text
【Memoria 语料 pilot · 协调人任务】

目标：按已冻结的 C0 规则，组织 2 名人类标注者独立标注 1 章开放许可教材（OpenStax Introduction to Business, Chapter 1, CC BY 4.0），产出可复核的 KP/语义边结果并计算人类 IAA。这不是发版，0.5 仍 HOLD。

你负责：分发材料、守独立性、组织培训/试标、跑校验、组织裁决、生成 IAA 报告、归档。
两名标注者：A 和 B，互相不看对方文件，标注前也不看任何已有机器草案。

材料：HUMAN-KIT.zip（含空白模板、培训 20、试标 10、工时表、裁决表、校验脚本；不含任何机器标签）
规则：ANNOTATION-MANUAL.md v1.1（唯一标注规则）
文本：chapter.txt（126,372 字符；Unicode code point 偏移，左闭右开）

流程 G0→G8（约 13–21 人类工时）：
G0 分发 + 独立性确认
G1 培训 20 项（各 ≥18/20）
G2 试标 10 项（各 ≥8/10；答案只在协调人处）
G3 正式 50 KP（45–55 可接受）→ 校验 exit 0 后才进 G4
G4 锁定 G3 后发 60 个候选对（无标签）
G5 60 对判定 edge/no_edge + 类型/方向/证据/置信 → 校验 exit 0
G6 生成差异表，组织 A/B/C 裁决
G7 生成人类 IAA 报告（强制 annotator_type=human；缺数据 exit 2，不伪造）
G8 归档：最终 jsonl + sha256 + TIME-LOG + 校验 JSON + IAA JSON + 裁决日志

必须遵守：
1. A/B 互不看、不讨论具体条目；规则疑问只找协调人；
2. G3 校验通过前，候选池不可见；
3. 不得用外部模型/网络代答；
4. 以 JSONL 文件交付，不接受口头结论；
5. 不伪造 IAA/不补空数据；缺数据就停下报 Lead。

交付目录（canonical）：
artifacts/corpus/pilot/human-kit/annotator-a/{kps.annotator-a.jsonl,pool-judgments.annotator-a.jsonl,trial-10.jsonl,adjudication-log.jsonl}
artifacts/corpus/pilot/human-kit/annotator-b/{...}
artifacts/corpus/pilot/human-kit/coordinator/{validation-*.json,ADJUDICATION-SHEET.generated.md,adjudication-summary.json,TIME-LOG.csv}
artifacts/agent/verify/corpus/pilot/human-iaa-report.json

命令：
python scripts/corpus/validate_human_labels.py --role a --kps <...> --pool-judgments <...> --json-out <...>
python scripts/corpus/make_adjudication_sheet.py --out <...> --json-out <...>
python scripts/corpus/make_iaa_report.py --adjudications <...> --out <...>

回传：把上述目录打包/只读副本 + 一段 10 行内摘要（完成/未完成文件、校验 exit、IAA 数字、工时、阻塞）交回。
```

## 二、协调人第一小时清单

1. 解压 `HUMAN-KIT.zip`，确认 17 个空白文件 + 手册 + chapter；
2. 建 A/B 两个独立目录，确认互不可见；
3. 读 `COORDINATOR-CHECKLIST.md` 与 `ANNOTATION-MANUAL.md` v1.1；
4. 约定 G1/G2 时间；答案 key 不放标注者目录；
5. 记录 `TIME-LOG.csv` 起止。

## 三、Lead 侧接收与判定

- 收到后先跑 `validate_human_labels.py`（A/B 各一次）；
- 校验 exit 0 才生成差异表/裁决/IAA；
- 人类 IAA 达 C8 线（span α≥0.67、κ≥0.67、edge F1≥0.70；裁决一致率≥0.80）才进入 pilot 报告与 0.5 重跑讨论；
- 不达线/缺数据 → 退回或修订手册，不把干跑值混入。

## 四、边界

- 不写用户库 `docs/example/**`；不改 C0 冻结稿；
- 不把机器草案 `kps.single.jsonl`/`edges.single.jsonl` 给标注者；
- 0.5 保持 HOLD。
