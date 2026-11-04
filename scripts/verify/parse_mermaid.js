#!/usr/bin/env node
/**
 * 仓库门禁：解析 Markdown 中的 ```mermaid 块（vendored mermaid）。
 *
 * 版本固定：
 *   - mermaid: src/memoria/ui/static/app/vendor/mermaid.min.js
 *              version 11.16.0，sha256=9198f6322f37f242a3396fbda15bec75a053095f9a81175340a3bb63ebd41b76
 *   - jsdom:   29.1.1，仅提供 DOMPurify 所需 DOM；依次尝试
 *              $MERMAID_JSDOM_API / <repo>/node_modules/jsdom / D:/deepseek-harness/node_modules/jsdom
 *   - node:    v24+
 *
 * 用法：node scripts/verify/parse_mermaid.js <md-file> [...] [--expect-blocks N]
 * 退出码：0=全 PASS；1=有块失败；2=用法/环境错误；3=致命错误。
 */
"use strict";
const fs = require("fs");
const vm = require("vm");
const crypto = require("crypto");
const path = require("path");
const { pathToFileURL } = require("url");

const REPO = path.resolve(__dirname, "..", "..");
const MERMAID_FILE = path.join(REPO, "src", "memoria", "ui", "static", "app", "vendor", "mermaid.min.js");
const EXPECTED_MERMAID_SHA = "9198f6322f37f242a3396fbda15bec75a053095f9a81175340a3bb63ebd41b76";
const EXPECTED_MERMAID_VERSION = "11.16.0";

function sha256File(p) {
  return crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

function extractBlocks(text) {
  const out = [];
  const re = /```mermaid\n([\s\S]*?)```/g;
  let m;
  while ((m = re.exec(text))) out.push(m[1]);
  return out;
}

function resolveJsdomApi() {
  const candidates = [
    process.env.MERMAID_JSDOM_API,
    path.join(REPO, "node_modules", "jsdom", "lib", "api.js"),
    "D:/deepseek-harness/node_modules/jsdom/lib/api.js",
    path.join(process.cwd(), "node_modules", "jsdom", "lib", "api.js"),
  ].filter(Boolean);
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  throw new Error("找不到 jsdom（设置 MERMAID_JSDOM_API 或安装 node_modules/jsdom）");
}

function jsdomVersion(apiPath) {
  try {
    const pkg = path.join(path.dirname(path.dirname(apiPath)), "package.json");
    return JSON.parse(fs.readFileSync(pkg, "utf8")).version;
  } catch (_) {
    return "unknown";
  }
}

(async () => {
  const args = process.argv.slice(2);
  let expectBlocks = null;
  const files = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--expect-blocks") {
      expectBlocks = Number(args[++i]);
    } else {
      files.push(args[i]);
    }
  }
  if (!files.length) {
    console.error("usage: node parse_mermaid.js <md-file> [...] [--expect-blocks N]");
    process.exit(2);
  }
  if (!fs.existsSync(MERMAID_FILE)) {
    console.error(`FATAL: vendored mermaid 不存在: ${MERMAID_FILE}`);
    process.exit(3);
  }
  const mermaidSha = sha256File(MERMAID_FILE);
  if (mermaidSha !== EXPECTED_MERMAID_SHA) {
    console.error(`FATAL: vendored mermaid sha 不匹配: ${mermaidSha}`);
    process.exit(3);
  }

  const jsdomApi = resolveJsdomApi();
  const { JSDOM } = await import(pathToFileURL(jsdomApi).href);
  const dom = new JSDOM("<!doctype html><html><body></body></html>", { pretendToBeVisual: true });
  for (const k of [
    "window", "document", "navigator", "HTMLElement", "SVGElement", "Node", "DOMParser",
    "XMLSerializer", "MutationObserver", "Element", "CustomEvent", "Text", "Image", "HTMLCanvasElement",
  ]) {
    if (dom.window[k] === undefined) continue;
    try {
      Object.defineProperty(globalThis, k, { value: dom.window[k], configurable: true, writable: true });
    } catch (_) {
      /* node 24 的内建 navigator 只读：跳过 */
    }
  }
  globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);

  const code = fs.readFileSync(MERMAID_FILE, "utf8");
  const verMatch = code.match(/version:"(\d+\.\d+\.\d+)"/);
  const mermaidVer = verMatch ? verMatch[1] : "unknown";
  if (mermaidVer !== EXPECTED_MERMAID_VERSION) {
    console.error(`FATAL: mermaid version 不匹配: ${mermaidVer}`);
    process.exit(3);
  }
  vm.runInThisContext(code, { filename: "mermaid.min.js" });
  const mermaid = globalThis.__esbuild_esm_mermaid_nm.mermaid.default;
  mermaid.initialize({ startOnLoad: false });

  console.log(JSON.stringify({
    kind: "meta", mermaidVersion: mermaidVer, mermaidSha256: mermaidSha,
    jsdomVersion: jsdomVersion(jsdomApi), node: process.version,
  }));

  let failed = 0;
  let totalBlocks = 0;
  for (const f of files) {
    const text = fs.readFileSync(f, "utf8");
    const blocks = extractBlocks(text);
    totalBlocks += blocks.length;
    console.log(JSON.stringify({ kind: "file", file: f, blocks: blocks.length, fileSha256: sha256File(f) }));
    for (let i = 0; i < blocks.length; i++) {
      try {
        const r = await mermaid.parse(blocks[i]);
        console.log(JSON.stringify({ kind: "block", file: f, index: i + 1, ok: true, diagramType: r.diagramType }));
      } catch (e) {
        failed++;
        console.log(JSON.stringify({
          kind: "block", file: f, index: i + 1, ok: false,
          error: String(e.message).split("\n").slice(0, 3).join(" | "),
        }));
      }
    }
  }
  if (expectBlocks !== null && totalBlocks !== expectBlocks) {
    failed++;
    console.log(JSON.stringify({ kind: "error", code: "BLOCK_COUNT_MISMATCH", expected: expectBlocks, actual: totalBlocks }));
  }
  console.log(JSON.stringify({ kind: "summary", failedBlocks: failed, totalBlocks }));
  process.exit(failed ? 1 : 0);
})().catch((e) => {
  console.error("FATAL", String(e.message).split("\n").slice(0, 3).join(" | "));
  process.exit(3);
});
