// _bugc_doc_check.js —— 检查交互剧本 fixture 文档的解析块分布（Bug C 回归定位用）
// 用法: node scripts/benchmark/maintenance/_bugc_doc_check.js <doc.md>
const fs = require("fs");
const vm = require("vm");
const path = require("path");

const REPO = path.resolve(__dirname, "../../..");
const JS = path.join(REPO, "src/memoria/ui/static/app/js");

const sandbox = { console };
sandbox.window = sandbox;
vm.createContext(sandbox);
for (const f of ["ast.js", "lexer.js", "parser.js"]) {
  vm.runInContext(fs.readFileSync(path.join(JS, f), "utf8"), sandbox, { filename: f });
}

const src = fs.readFileSync(process.argv[2], "utf8");
const doc = sandbox.MemoriaParser.parse(src);
const counts = {};
doc.blocks.forEach((b) => (counts[b.type] = (counts[b.type] || 0) + 1));
console.log("总块数:", doc.blocks.length);
console.log("类型分布:", JSON.stringify(counts));
const lists = doc.blocks.filter((b) => b.type === "list");
console.log("列表块数:", lists.length);
lists.slice(0, 6).forEach((b, i) =>
  console.log(
    "  list[" + i + "] src=" + b.srcLine + ".." + b.srcLineEnd +
    " items=" + b.items.length + " itemSrcLine=" + JSON.stringify(b.itemSrcLine)
  )
);
