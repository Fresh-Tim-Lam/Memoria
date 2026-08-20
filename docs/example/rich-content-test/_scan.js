// Scan test-content.md: find any line where [[\ syntax is NOT parsed as highlight/font node
const fs = require("fs");
const path = require("path");
global.window = global;
const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
for (const f of ["ast.js", "lexer.js", "parser.js"]) {
  eval(fs.readFileSync(path.join(JS, f), "utf8"));
}
const parser = window.MemoriaParser;
const lexer = window.MemoriaLexer;

const body = fs.readFileSync("d:/AAA_Jupyter/Memoria/docs/example/rich-content-test/test-content.md", "utf8");
const doc = parser.parse(body);

let issues = 0;
const lines = body.split("\n");
for (let i = 0; i < lines.length; i++) {
  const line = lines[i];
  if (!line.includes("[[\\")) continue;
  const toks = lexer.tokenize(line);
  const hasOpen = toks.some(t => t.type === "highlight_open" || t.type === "font_color_open" ||
    t.type === "font_size_open" || t.type === "font_bold_open" || t.type === "font_italic_open" ||
    t.type === "font_underline_open" || t.type === "font_superscript_open" || t.type === "font_subscript_open");
  if (!hasOpen) {
    console.log(`L${i + 1}: NO font-open token: ${line}`);
    issues++;
    continue;
  }
  // parse the line as inline
  const nodes = parser.parseInline(toks);
  const raw = JSON.stringify(nodes);
  if (raw.includes("[[\\")) {
    console.log(`L${i + 1}: literal [[\\ text remains in AST: ${line}`);
    issues++;
  }
}
console.log("issues: " + issues);
