# `-src-block` 计数探针（0.4.7 任务 4 修补验证）

- 开始：2026-10-23T07:24:03.253542+00:00
- 用时：21.2s
- 结论：✅ PASS

| 检查 | 结果 | 详情 |
|---|---|---|
| B0-ready | ✅ | `{"setup": "opened"}` |
| B1-dom-count-eq-ast-count | ✅ | `{"domCount": 22, "astCount": 22, "diff": 0}` |
| B2-block-index-unique | ✅ | `{"dupIdx": []}` |
| B3-block-index-complete | ✅ | `{"missing": [], "outOfRange": [], "nullIdx": 0}` |
| B4-nested-not-self-block | ✅ | `{"nestedCount": 4, "nestedWithSrcBlockClass": 0}` |
