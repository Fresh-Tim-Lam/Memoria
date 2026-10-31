# 记忆卡：release-manager

<!-- team-memory-card/v1 · bounded to 8 KiB · omitted 0 older section(s) · truncated: false -->

## release-manager · release_preflight 补卫：version.md「说明」行的"最近已发布版本"必须与实际 tag 一致（今天已真实误导过一次排期）
<!-- task-id: task-167 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-167「release_preflight 补卫：version.md「说明」行的"最近已发布版本"必须与实际 tag 一致（今天已真实误导过一次排期）」：artifacts/agent/verify/todo/release-preflight-version-consistency.md, scripts/agent/release_preflight.py, scripts/agent/test_release_preflight.py
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）



## release-manager · 🔴 修构建管线：禁止 config 私有文件进 zip + 出具已泄露版本的资产替换方案
<!-- task-id: task-185 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-185「🔴 修构建管线：禁止 config 私有文件进 zip + 出具已泄露版本的资产替换方案」：artifacts/agent/verify/release-format/api-key-leak-incident.md, packaging/make_release_zip.py, src/memoria/services/verify/manifest.py, scripts/agent/release_format_gate.py, scripts/agent/release_manifest.py, scripts/agent/release_preflight.py, tests/test_release_format.py, docs/design/release-format.md, artifacts/release-checklist-v0.4.10.md, artifacts/release-body-v0.4.10.md, dist-release/clean-v0.4.9/Memoria-v0.4.9-win64-lite.zip, dist-release/clean-v0.4.9/Memoria-v0.4.9-win64.zip
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
- 工具 write 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\scripts\agent\release_manifest.py": file has not been read — read the file, then retry
- 工具 write 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\scripts\agent\release_format_gate.py": file has not been read — read the file, then retry
- 工具 write 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\artifacts\release-checklist-v0.4.10.md": file has not been read — read the file, then retry
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\docs\design\release-format.md": file has not been read — read the file, then retry
- 工具 edit 失败：Error: cannot modify "D:\AAA_Jupyter\Memoria\artifacts\release-body-v0.4.10.md": file has not been read — read the file, then retry
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）


## release-manager · 许可改为 AGPL-3.0 + 商业授权（B2）：依赖许可审计 + CLA + LICENSE/LICENSING/TRADEMARK/THIRD-PARTY 全套
<!-- task-id: task-207 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-207「许可改为 AGPL-3.0 + 商业授权（B2）：依赖许可审计 + CLA + LICENSE/LICENSING/TRADEMARK/THIRD-PARTY 全套」：LICENSE, README.md, README.cn.md, pyproject.toml, packaging/build.py, packaging/templates/README.release.txt, docs/marketing/claims.md, artifacts/agent/verify/license/AUDIT.md, artifacts/agent/verify/license/audit.json
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）

## release-manager · 发版前置·工作区脏文件分类与提交/忽略/删除提案
<!-- task-id: task-275 -->
### 我确认的事实（带证据：file:line / commit / 命令输出）
authority: machine
- 完成任务 task-275「发版前置·工作区脏文件分类与提交/忽略/删除提案」：artifacts/agent/verify/release-manager/triage-20261031/report.md, artifacts/agent/verify/release-manager/triage-20261031/benchmark-appendix.md, artifacts/agent/verify/release-manager/triage-20261031/benchmark-commit.txt, artifacts/agent/verify/release-manager/triage-20261031/benchmark-quarantine.txt, artifacts/agent/verify/release-manager/triage-20261031/benchmark-ignore.txt, artifacts/agent/verify/release-manager/triage-20261031/root-quarantine.txt, artifacts/agent/verify/release-manager/triage-20261031/resources-quarantine.txt, artifacts/agent/verify/release-manager/triage-20261031/gitignore-append.txt
### 我试过但失败的路（含失败原因 —— 比成功经验更省时间）
authority: machine
（本段会话没有记录到失败的调用）
### 我留下的坑 / 下一个人该从哪开始
authority: machine
（没有未完成任务；从本段会话的结论继续）
### 我推翻过的假设
authority: machine
- （未自动分类；复查上方机器事实时请人工标注被推翻项）
