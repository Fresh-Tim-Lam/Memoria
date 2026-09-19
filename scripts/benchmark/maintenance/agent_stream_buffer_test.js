#!/usr/bin/env node
/* AG11 门禁：流式中间缓冲 VM 单测（agent-stream-buffer.js 的纯分割器）。
   载入真实 agent-stream-buffer.js，逐场景断言 {safe, pending, openBlock} 与
   `safe + pending === 输入`（切刀不丢字、不重复）。
   用法：node scripts/benchmark/maintenance/agent_stream_buffer_test.js
*/
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "agent-stream-buffer.js");
const code = fs.readFileSync(SRC, "utf8");

function fresh() {
  const sandbox = {};
  sandbox.globalThis = sandbox;
  const ctx = vm.createContext(sandbox);
  vm.runInContext(code, ctx, { filename: "agent-stream-buffer.js" });
  return ctx.MemoriaStreamBuffer;
}

let failures = 0;
function check(name, cond, extra) {
  console.log((cond ? "PASS" : "FAIL") + "  " + name + (extra ? "  " + JSON.stringify(extra) : ""));
  if (!cond) failures += 1;
}

/** 每个场景都必须满足的两条不变量：safe+pending===输入、safe 以换行收尾或为空。 */
function invariants(B, input, out) {
  check("  不变量 safe+pending===输入", out.safe + out.pending === input, { safe: out.safe, pending: out.pending });
  check("  不变量 safe 以换行收尾（或空串）", out.safe === "" || out.safe.charAt(out.safe.length - 1) === "\n", { safe: out.safe });
}

const B = fresh();
check("模块导出 split", B && typeof B.split === "function");

// 1) 空串
{
  const input = "";
  const out = B.split(input);
  check("1 空串 ⇒ 全空、无构造", out.safe === "" && out.pending === "" && out.openBlock === "", out);
  invariants(B, input, out);
}

// 2) 已完成的普通文本（无未闭合构造）⇒ 全部安全，行为不变
{
  const input = "# 标题\n\n这是第一段。\n第二段也完成了。\n";
  const out = B.split(input);
  check("2 完整文本 ⇒ 全部 safe、openBlock 空", out.safe === input && out.pending === "" && out.openBlock === "", out);
  invariants(B, input, out);
}

// 3) 正在到达的一行（末尾无 \n）⇒ 只扣那一行
{
  const input = "第一行完成。\n第二行还在到";
  const out = B.split(input);
  check("3 半行 ⇒ safe=完整行、pending=半行、line",
    out.safe === "第一行完成。\n" && out.pending === "第二行还在到" && out.openBlock === "line", out);
  invariants(B, input, out);
}

// 4) 表格：完整行即可渲染，半截行待补
{
  const input = "| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3";
  const out = B.split(input);
  check("4 表格 ⇒ 表头与首数据行进 safe、半截下一行进 pending、line",
    out.safe === "| a | b |\n| --- | --- |\n| 1 | 2 |\n" && out.pending === "| 3" && out.openBlock === "line", out);
  invariants(B, input, out);
}

// 5) 未闭合围栏（无 info string）⇒ 从围栏行起整段扣住
{
  const input = "前面的话。\n```\ncode line\n";
  const out = B.split(input);
  check("5 未闭合 fence（无 info）⇒ safe=围栏前、pending=整块、fence",
    out.safe === "前面的话。\n" && out.pending === "```\ncode line\n" && out.openBlock === "fence", out);
  invariants(B, input, out);
}

// 6) 未闭合围栏（带 info string）
{
  const input = "```js\nconst a = 1;\n";
  const out = B.split(input);
  check("6 未闭合 fence（带 info）⇒ 整块 pending、fence",
    out.safe === "" && out.pending === input && out.openBlock === "fence", out);
  invariants(B, input, out);
}

// 7) 围栏先闭合、再重新开启（新的那个未闭合）⇒ 只扣第二次开启处
{
  const input = "```\nold\n```\n中间文字。\n```py\nnew\n";
  const out = B.split(input);
  check("7 fence 闭合后再开启 ⇒ safe 含前半+中间、pending 从第二个围栏起、fence",
    out.safe === "```\nold\n```\n中间文字。\n" && out.pending === "```py\nnew\n" && out.openBlock === "fence", out);
  invariants(B, input, out);
}

// 7b) 围栏正常闭合（无残留）⇒ 全部 safe
{
  const input = "```\ncode\n```\n收尾。\n";
  const out = B.split(input);
  check("7b fence 闭合 ⇒ 全部 safe、openBlock 空", out.safe === input && out.pending === "" && out.openBlock === "", out);
  invariants(B, input, out);
}

// 7c) 不同围栏字符不能互相关闭（``` 开的必须 ``` 关，~~~ 不算）
{
  const input = "```\ncode\n~~~\n还是代码\n";
  const out = B.split(input);
  check("7c 异类围栏不闭合 ⇒ 仍 fence 整块 pending",
    out.safe === "" && out.pending === input && out.openBlock === "fence", out);
  invariants(B, input, out);
}

// 8) 未闭合 $$ 公式块
{
  const input = "推导如下：\n$$\nx = 1\n";
  const out = B.split(input);
  check("8 未闭合 $$ ⇒ safe=公式前、pending=整块、math",
    out.safe === "推导如下：\n" && out.pending === "$$\nx = 1\n" && out.openBlock === "math", out);
  invariants(B, input, out);
}

// 8b) 单行内自闭合 $$...$$ 不算开启
{
  const input = "行内 $$x=1$$ 结束。\n";
  const out = B.split(input);
  check("8b 单行自闭合 $$ ⇒ 全部 safe、无 math", out.safe === input && out.pending === "" && out.openBlock === "", out);
  invariants(B, input, out);
}

// 9) 未闭合的文首 frontmatter
{
  const input = "---\ntitle: 测试\ntags: [a]\n";
  const out = B.split(input);
  check("9 未闭合 frontmatter ⇒ 全扣、frontmatter",
    out.safe === "" && out.pending === input && out.openBlock === "frontmatter", out);
  invariants(B, input, out);
}

// 9b) frontmatter 闭合后接正文 ⇒ 正文照常逐行
{
  const input = "---\ntitle: 测试\n---\n正文第一行。\n正文第二行";
  const out = B.split(input);
  check("9b frontmatter 闭合 ⇒ 后续正文进 safe、半行进 pending、line",
    out.safe === "---\ntitle: 测试\n---\n正文第一行。\n" && out.pending === "正文第二行" && out.openBlock === "line", out);
  invariants(B, input, out);
}

// 10) 综合：表格 → 未闭合围栏 → 关闭并续写
{
  const input = "| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 |\n```txt\n未完\n";
  const out = B.split(input);
  check("10 表格完整后接未闭合 fence ⇒ safe=完整表格、pending=fence、fence",
    out.safe === "| a | b |\n| --- | --- |\n| 1 | 2 |\n| 3 |\n" && out.pending === "```txt\n未完\n" && out.openBlock === "fence", out);
  invariants(B, input, out);

  const closed = input + "```\n结尾。\n";
  const out2 = B.split(closed);
  check("10b 围栏补全后 ⇒ 全部 safe、无构造", out2.safe === closed && out2.pending === "" && out2.openBlock === "", out2);
  invariants(B, closed, out2);
}

console.log(failures ? `\nAG11 VM 单测：${failures} 项失败` : "\nAG11 VM 单测：全 PASS（frontmatter/fence/math/半行 + 不变量）");
process.exit(failures ? 1 : 0);
