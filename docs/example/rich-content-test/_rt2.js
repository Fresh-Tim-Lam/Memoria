// Round-trip: parse -> generate -> re-parse -> generate, check identity
const fs = require("fs");
const path = require("path");
global.window = global;

const JS = "d:/AAA_Jupyter/Memoria/src/memoria/ui/static/m0/js/";
for (const f of ["ast.js", "lexer.js", "parser.js", "source-gen.js"]) {
  eval(fs.readFileSync(path.join(JS, f), "utf8"));
}
const parser = window.MemoriaParser;
const G = window.MemoriaSourceGen;

function dump(nodes, ind) {
  const pad = " ".repeat(ind || 0);
  return nodes.map(n => {
    const extra = n.type === "text" ? `(${JSON.stringify(n.content)})` : n.type === "highlight" ? `[bg=${n.color},fg=${n.fgColor}]` : "";
    if (n.children && n.children.length) return `${pad}${n.type}${extra}{\n${dump(n.children, (ind || 0) + 2)}\n${pad}}`;
    return `${pad}${n.type}${extra}`;
  }).join("\n");
}

const cases = [
  "[[\\h:blue:purple|*是****的***]]",
  "[[\\h:blue:purple| *是* ** *的* ** ]]",
  "[[\\h:blue:purple|*是* ***的***]]",
];
for (const line of cases) {
  const doc = parser.parse(line);
  const para = doc.blocks.find(b => b.type === "paragraph");
  const gen = G.generateBlock(para);
  const doc2 = parser.parse(gen);
  const para2 = doc2.blocks.find(b => b.type === "paragraph");
  const gen2 = G.generateBlock(para2);
  const same = gen === gen2;
  console.log("SRC:   " + line);
  console.log("GEN1:  " + gen);
  console.log("GEN2:  " + gen2 + "  roundtrip stable: " + same);
  if (!same) {
    console.log("AST1:\n" + dump(para.children, 2));
    console.log("AST2:\n" + dump(para2.children, 2));
  }
  console.log("");
}
