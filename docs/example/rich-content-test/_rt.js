// sourceGen round-trip test
const fs = require("fs");
const path = require("path");
global.window = global;
const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js"]) {
  eval(fs.readFileSync(path.join(JS, f), "utf8"));
}
const parser = window.MemoriaParser;
const G = window.MemoriaSourceGen;

const cases = [
  "[[\\h:blue:purple| *是* ** *的* ** ]]",
  "[[\\h:blue:purple|*是* ***的***]]",
  "[[\\h:#ff5500:#000000|**?** *底* ***黑字*** ]]",
  "[[\\h:blue|**啊实**]][[\\h:blue:purple|**打实a|**]]",
];
for (const line of cases) {
  const doc = parser.parse(line);
  const para = doc.blocks.find(b => b.type === "paragraph");
  const out = G.generateBlock(para);
  console.log("IN : " + JSON.stringify(line));
  console.log("OUT: " + JSON.stringify(out));
  console.log("same: " + (out === line));
  console.log("");
}
