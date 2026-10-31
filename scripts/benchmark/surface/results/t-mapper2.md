# 多级列表 Tab/Shift+Tab 真机探针（N4）

- 开始：2026-10-23T07:24:55.758935+00:00
- 用时：26.3s
- 结论：✅ PASS

| 检查 | 结果 | 详情 |
|---|---|---|
| T0-setup | ✅ | `{"setup": "opened", "body": "# 多级列表测试文档\n\n本节用于验证多级列表（嵌套列表）的解析、渲染与编辑行为。\n\n## 基本两级\n\n- 第一项\n  - 子项 A\n  - 子项 B\n- 第二项\n\n## 三级嵌套\n\n- 甲\n  - 乙一级\n    - 丙二级\n  - 乙另一"}` |
| T0b-list-block-found | ✅ | `{"listBlockIdx": 6}` |
| DIAG-hit | ✅ | `{"tag": "LI", "liText": "子项 B", "liIdxInAll": 2, "allLiTexts": ["第一项子项 ", "子项 A", "子项 B", "第二项"]}` |
| T0c-click-lands-on-target | ✅ | `{"listItemIndex": 2, "want": 2, "point": {"x": 365, "y": 325, "wantText": "子项 B"}}` |
| DIAG-t1 | ✅ | `{"hasEH": true, "hasES": true, "cursorAST": {"bi": 6, "np": [0], "off": 0}, "editMode": true, "listItemIndex": 2, "ret": false, "err": null, "fns": {"flatLi": "undefined"}}` |
| T1-list-tab-indent | ✅ | `{"body": "# 多级列表测试文档\n\n本节用于验证多级列表（嵌套列表）的解析、渲染与编辑行为。\n\n## 基本两级\n\n- 第一项\n  - 子项 A\n    - 子项 B\n- 第二项\n\n## 三级嵌套\n\n- 甲\n  - 乙一级\n    - 丙二级\n  - 乙另一\n- 戊\n\n## 有序子列表\n\n- 外层\n  1. 有序一\n  2. 有序二\n- 外层二\n\n## 普通段落（用于 Tab 插空格测试）\n\nplain para for tab\n\n结束语。\n"}` |
| T2-list-shifttab-outdent | ✅ | `{"t1Changed": true, "body": "# 多级列表测试文档\n\n本节用于验证多级列表（嵌套列表）的解析、渲染与编辑行为。\n\n## 基本两级\n\n- 第一项\n  - 子项 A\n  - 子项 B\n- 第二项\n\n## 三级嵌套\n\n- 甲\n  - 乙一级\n    - 丙二级\n  - 乙另一\n- 戊\n\n## 有序子列表\n\n- 外层\n  1. 有序一\n  2. 有序二\n- 外层二\n\n## 普通段落（用于 Tab 插空格测试）\n\nplain para for tab\n\n结束语。\n"}` |
| T3-paragraph-tab-spaces | ✅ | `{"body": " 乙一级\n    - 丙二级\n  - 乙另一\n- 戊\n\n## 有序子列表\n\n- 外层\n  1. 有序一\n  2. 有序二\n- 外层二\n\n## 普通段落（用于 Tab 插空格测试）\n\n    plain para for tab\n\n结束语。\n"}` |
