// Memoria i18n 引擎自测（Node，无依赖）：
//   node scripts/i18n_selftest.js
// 校验默认语言/切换持久化/缺键回退链/参数填充。全部 PASS 退出码 0。
const fs = require("fs");
const path = require("path");

const APP = path.join(__dirname, "..", "src", "memoria", "ui", "static", "app");
let store = {};
globalThis.localStorage = {
  getItem: (k) => (k in store ? store[k] : null),
  setItem: (k, v) => { store[k] = String(v); },
};
globalThis.document = null; // applyStatic 空转（需全局 document 存在）

function load(f) {
  const code = fs.readFileSync(path.join(APP, f), "utf-8");
  new Function("window", "globalThis", code)(globalThis, globalThis);
}
load("i18n/zh-CN.js");
load("i18n/en.js");
load("js/i18n.js");

const I = globalThis.MemoriaI18n;
const results = [];
function eq(name, got, want) {
  const ok = got === want;
  results.push(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : `: got=${JSON.stringify(got)} want=${JSON.stringify(want)}`}`);
}

eq("defaultLang", I.currentLang(), "zh-CN");
eq("t zh toolbar.open", I.t("toolbar.open"), "打开");
eq("switch en + persist", (I.setLang("en"), I.currentLang()), "en");
eq("t en after switch", I.t("toolbar.open"), "Open");
eq("t zh fallback when en missing", I.t("app.status.ready"), "Ready");
eq("key missing in both -> key", I.t("definitely.missing"), "definitely.missing");
eq(
  "param fill",
  I.t("settings.display.fontDefault", { def: 14, min: 12, max: 28 }),
  "Default 14px, range 12\u201328px."
);
eq("langDisplay zh", I.langDisplay("zh-CN"), "中文（简体）");
// —— 方案 1：后端检查消息 code/params（rawLookup 无回退；en 有模板、zh 不复制）——
eq(
  "rawLookup en has backend code",
  typeof I.rawLookup("en", "check.issue.orphan_md"),
  "string"
);
eq(
  "rawLookup zh has no backend code (message stays backend)",
  I.rawLookup("zh-CN", "check.issue.orphan_md"),
  null
);
eq("switch en + backend issue fill", (I.setLang("en"), I.t("check.issue.orphan_md", { rel: "a.md" })), "Document is missing metadata config: a.md");
eq("switch back zh", (I.setLang("zh-CN"), I.t("toolbar.open")), "打开");
console.log(results.join("\n"));
process.exit(results.some((r) => r.startsWith("FAIL")) ? 1 : 0);
