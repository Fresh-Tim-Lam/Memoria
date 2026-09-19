#!/usr/bin/env node
/* 文件树图标 VM 单测（2026-09-19）：载入**真实** file-tree.js，校验借用的 dsh 图标
   （见 file-tree.js 末尾块 B / THIRD_PARTY_NOTICES.md）与文件类型分类器。
   - 渲染面 `window.MemoriaTreeIcons` 由该文件末尾块的 `typeof window !== "undefined"` 分支暴露；
     本测试把 sandbox.window 指向 sandbox 本身，即可在无 DOM 环境下拿到同一份实现。
   - file-tree.js 顶层只定义函数/常量（`renderFileTree` 等不会在载入时执行），故可独立 VM 载入。
   用法：node scripts/benchmark/maintenance/file_tree_icons_test.js
*/
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "..", "..", "src", "memoria", "ui", "static", "app", "js", "file-tree.js");
const code = fs.readFileSync(SRC, "utf8");

function fresh() {
  const sandbox = {};
  sandbox.globalThis = sandbox;
  sandbox.window = sandbox; // file-tree.js 顶层即 `window.MemoriaFileTree = (…)()`
  const ctx = vm.createContext(sandbox);
  vm.runInContext(code, ctx, { filename: "file-tree.js" });
  return sandbox;
}

let failures = 0;
function check(name, cond, extra) {
  console.log((cond ? "PASS" : "FAIL") + "  " + name + (extra !== undefined ? "  " + JSON.stringify(extra) : ""));
  if (!cond) failures += 1;
}

const SB = fresh();
const I = SB.MemoriaTreeIcons;
check("A1 载入后可取 window.MemoriaTreeIcons", !!I && typeof I.icon === "function", typeof I);
check("A2 file-tree.js 仍导出 window.MemoriaFileTree（render/expandToPath/revealDir）",
  !!SB.MemoriaFileTree && ["init", "render", "expandToPath", "revealDir"].every((k) => typeof SB.MemoriaFileTree[k] === "function"),
  SB.MemoriaFileTree ? Object.keys(SB.MemoriaFileTree) : null);

// ---- 1) 图标齐全 -----------------------------------------------------------
const REQUIRED = [
  // 树结构：展开三角 / 目录 close+open / 缩进折角
  "triangleRight", "folderClose", "folderOpen", "treeCorner",
  // 文件类型类目（dsh FileTypeIcon 口径；folder 另见 ftFolder）
  "ftMarkdown", "ftCode", "ftImage", "ftHtml", "ftPdf", "ftPpt", "ftVideo", "ftWord", "ftExcel", "ftOther", "ftFolder",
];
const missing = REQUIRED.filter((n) => typeof I.icon(n) !== "string" || I.icon(n) === "");
check("B1 必需图标全部存在且非空", missing.length === 0, { missing });
check("B2 names 覆盖全部必需图标", REQUIRED.every((n) => I.names.indexOf(n) >= 0), { names: I.names.length });

// ---- 2) 每个图标都是「单 currentColor」的完好 SVG ---------------------------
const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\s*\(|var\(\s*--dsw|fill="(?!currentColor)[a-zA-Z#]/;
for (const name of REQUIRED) {
  const svg = I.icon(name, "cls-" + name);
  const colorCount = (svg.match(/currentColor/g) || []).length;
  const open = (svg.match(/<svg\b/g) || []).length;
  const close = (svg.match(/<\/svg>/g) || []).length;
  const paths = (svg.match(/<path\b/g) || []).length;
  const selfClosed = (svg.match(/<path\b[^>]*\/>/g) || []).length;
  const okShape = svg.startsWith("<svg ") && svg.endsWith("</svg>") && open === 1 && close === 1;
  const okColor = colorCount === 1 && svg.indexOf('fill="currentColor"') >= 0;
  const okViewBox = /viewBox="[-\d. ]+"/.test(svg);
  const okClass = svg.indexOf('class="cls-' + name + '"') >= 0;
  const okNoLiteral = !COLOR_LITERAL.test(svg.replace(/fill="currentColor"/g, ""));
  check("C:" + name + " 单 currentColor / 完好 SVG / 无硬编码颜色 / 带 viewBox+class",
    okShape && okColor && okViewBox && okClass && okNoLiteral && paths >= 1 && selfClosed === paths,
    { colorCount, open, close, paths, selfClosed, okViewBox, okClass });
}

// 未知图标名静默返回空串（不得抛错）
check("C:X 未知图标名返回空串", I.icon("no-such-icon") === "" && I.icon(undefined) === "");

// ---- 3) 文件类型分类器 -----------------------------------------------------
const CASES = [
  ["note.md", "markdown"], ["a/b/CHANGELOG.md", "markdown"], ["README", "markdown"], ["x.markdown", "markdown"],
  ["main.py", "code"], ["app.js", "code"], ["data.json", "code"], ["style.css", "code"], ["a.yml", "code"],
  ["pic.png", "image"], ["photo.JPG", "image"], ["icon.svg", "image"],
  ["page.html", "html"],
  ["manual.pdf", "pdf"],
  ["slides.pptx", "ppt"],
  ["clip.mp4", "video"],
  ["report.docx", "word"],
  ["sheet.xlsx", "excel"],
  ["LICENSE", "other"], ["noext", "other"], ["a.unknownext", "other"], ["", "other"],
];
const bad = [];
for (const [p, want] of CASES) {
  const got = I.classifyFileType(p);
  if (got !== want) bad.push({ path: p, want, got });
}
check("D1 扩展名/文件名 → 类目映射全部正确", bad.length === 0, { bad });

const catBad = Object.keys(I.categories).filter((c) => typeof I.categories[c] !== "string" || !I.names.includes(I.categories[c]));
check("D2 每个类目都指向已定义图标", catBad.length === 0, { catBad });

// ---- 4) 缩进连接线 ---------------------------------------------------------
check("E1 depth 0 不产出连接线", I.treeGuides(0) === "");
const g2 = I.treeGuides(2);
check("E2 depth 2 = 1 段导轨 + 1 个折角 + 1 个 treeCorner svg",
  (g2.match(/-tree-guide-rail/g) || []).length === 1
  && (g2.match(/-tree-guide-corner/g) || []).length === 1
  && (g2.match(/<svg\b/g) || []).length === 1
  && g2.indexOf('viewBox="-0.5 0 8.5 10.5"') >= 0,
  g2);
const g3 = I.treeGuides(3);
check("E3 depth 3 = 2 段导轨 + 1 个折角",
  (g3.match(/-tree-guide-rail/g) || []).length === 2 && (g3.match(/-tree-guide-corner/g) || []).length === 1);

console.log(failures ? `\n文件树图标 VM 单测：${failures} 项失败` : "\n文件树图标 VM 单测：全 PASS（图标清单 / 单 currentColor / 分类器 / 连接线）");
process.exit(failures ? 1 : 0);
