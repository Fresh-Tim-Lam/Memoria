# 多级列表 Tab/Shift+Tab 真机探针（N4）

- 开始：2026-10-23T06:56:39.142264+00:00
- 用时：26.5s
- 结论：❌ FAIL

| 检查 | 结果 | 详情 |
|---|---|---|
| T0-setup | ✅ | `{"setupMode": "direct", "body": "- a\n  - b\n  - c\n- d\n\nplain para for tab"}` |
| T1-list-tab-indent | ✅ | `{"body": "- a\n  - b\n  - c\n- d\n\nplain para for tab"}` |
| T2-list-shifttab-outdent | ❌ | `{"body": "- a\n  - b\n  - c\n- d\n\nplain para for tab"}` |
| T3-paragraph-tab-spaces | ❌ | `{"place": "no-para"}` |
