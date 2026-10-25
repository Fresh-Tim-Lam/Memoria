# 样例插件：`kb-stats`（S4 第三方声明式加工具）

> 这是 **S4 交付物的可运行样例**：第三方**不改 Memoria 核心（`registry.py` 本体）**，
> 只写一份声明 + 自己的脚本，就能给 agent 增加工具。

## 文件

| 文件 | 谁的 | 说明 |
|---|---|---|
| `plugin.json.template` | 插件作者 | **声明**（`provides.tools[].impl` 指定"怎么启动我的工具"） |
| `kb_stats_tool.py` | 插件作者 | 真正干活的代码（读 stdin 的 JSON 请求、写 stdout 的 JSON 结果） |
| `slow_tool.py` / `big_tool.py` | 测试用 | 分别验证超时与输出上限被**真强制** |
| `check.py` | 验收脚本 | 落地样例 + 逐条断言（含"39 把内置工具逐项不变"） |

## 声明形态（v1）

```jsonc
{
  "v": 1, "id": "kb-stats", "name": "知识库统计（样例）",
  "provides": {"tools": [
    {"tool_id": "ext.kb_stats",
     "impl": {"kind": "stdio",
              "command": ["python", "<插件目录>/kb_stats_tool.py"],
              "timeout_s": 20,
              "description": "统计库里的 md 篇数/行数/标题行数",
              "input_schema": {"type": "object", "properties": {"glob": {"type": "string"}}}}}
  ]},
  "permissions": {"read": ["**"], "write": []},
  "approval": {"read": "auto", "write": "confirm"}
}
```

- `tool_id` **必须**以 `ext.` 命名空间开头（内置名保留，冲突在装载期就被拒）；
- **默认关闭**：库级注册表 `<kb>/.memoria/agent/capabilities.json` 里没有显式启用它 ⇒ 工具不出现；
- v1 **只允许只读扩展工具**（`read_only: true`）；声明 `read_only: false` ⇒ 装载期 `ext_write_not_allowed`。

## 🔴 边界声明（原文照抄，不许软化）

```
扩展工具是【用户显式安装的任意代码】，不是沙箱；
`read_only` 仅参与审批档判定，不构成执行强制；
要受 W1–W4 保护，必须走内置 propose_write 链路，而不是在扩展工具里直接写文件。
```

具体含义：子进程完全可以自己 `open(path, "w")` 写文件 —— **那条路径在 W1 写者链之外**，
W1（入口唯一）/ W2（读后写）/ W3（写前备份）**都不保护**它。
所以**不能**说"扩展工具不新增写者"；准确说法是"**扩展工具在 W1 写者链之外**"。

## 运行

```bash
python artifacts/agent/verify/todo/s4_sample_plugin/check.py --json artifacts/agent/verify/todo/s4-extension.json
```
