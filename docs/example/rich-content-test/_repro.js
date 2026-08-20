// Node harness: load AST/Lexer/Parser and reproduce highlight parse
const fs = require("fs");
const path = require("path");

global.window = global;

const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
eval(fs.readFileSync(path.join(JS, "ast.js"), "utf8"));
eval(fs.readFileSync(path.join(JS, "lexer.js"), "utf8"));
eval(fs.readFileSync(path.join(JS, "parser.js"), "utf8"));

const lexer = window.MemoriaLexer;
const parser = window.MemoriaParser;
const T = window.MemoriaAST.TYPES;

function dumpNode(n, indent) {
  const pad = " ".repeat(indent);
  switch (n.type) {
    case T.TEXT: return `${pad}text(${JSON.stringify(n.content)})`;
    case T.HIGHLIGHT: return `${pad}highlight[bg=${n.color},fg=${n.fgColor}]{\n${n.children.map(c => dumpNode(c, indent + 2)).join("\n")}\n${pad}}`;
    case T.FONT_COLOR: return `${pad}font_color[${n.color}]{\n${n.children.map(c => dumpNode(c, indent + 2)).join("\n")}\n${pad}}`;
    case T.BOLD: return `${pad}bold{\n${n.children.map(c => dumpNode(c, indent + 2)).join("\n")}\n${pad}}`;
    case T.ITALIC: return `${pad}italic{\n${n.children.map(c => dumpNode(c, indent + 2)).join("\n")}\n${pad}}`;
    case T.BOLD_ITALIC: return `${pad}bold_italic{\n${n.children.map(c => dumpNode(c, indent + 2)).join("\n")}\n${pad}}`;
    default: return `${pad}${n.type}:${JSON.stringify(n.content || n.code || "")}`;
  }
}

const cases = [
  "[[\\h:blue:purple| *是* ** *的* ** ]]",
  "[[\\h:blue:purple|*是* ***的***]]",
  "[[\\h:blue:purple|*是****的***]]",
];

for (const src of cases) {
  console.log("=".repeat(70));
  console.log("SOURCE:", src);
  const toks = lexer.tokenize(src);
  console.log("TOKENS:", toks.map(t => `${t.type}(${JSON.stringify(t.value)})`).join(" "));
  const nodes = parser.parseInline(toks);
  console.log("AST:");
  nodes.forEach(n => console.log(dumpNode(n, 2)));
}
