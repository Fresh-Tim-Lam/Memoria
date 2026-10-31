# `-src-block` 计数探针（0.4.7 任务 4 修补验证）

- 开始：2026-10-23T07:23:30.861983+00:00
- 用时：19.7s
- 结论：❌ FAIL

| 检查 | 结果 | 详情 |
|---|---|---|
| B0-ready | ✅ | `{"setup": "opened"}` |
| B1-dom-count-eq-ast-count | ❌ | `{"domCount": 22, "astCount": 0, "diff": 22}` |
| B2-block-index-unique | ✅ | `{"dupIdx": []}` |
| B3-block-index-complete | ❌ | `{"missing": [], "outOfRange": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21], "nullIdx": 0}` |
| B4-nested-not-self-block | ✅ | `{"nestedCount": 4, "nestedWithSrcBlockClass": 0}` |
