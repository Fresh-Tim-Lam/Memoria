// 临时测试：验证 highlight 内强调的解析
global.window = global;
require("./src/memoria/ui/static/m0/js/ast.js");
require("./src/memoria/ui/static/m0/js/lexer.js");
require("./src/memoria/ui/static/m0/js/parser.js");
require("./src/memoria/ui/static/m0/js/source-gen.js");
const Lexer = global.MemoriaLexer;
const Parser = global.MemoriaParser;
const G = global.MemoriaSourceGen;

function parseInline(src) {
  return Parser.parseInline(Lexer.tokenize(src));
}

function roundTrip(src) {
  const ast = parseInline(src);
  const gen1 = G.generateInlineList(ast);
  const ast2 = parseInline(gen1);
  const gen2 = G.generateInlineList(ast2);
  return { ast, gen1, gen2, stable: gen1 === gen2 && JSON.stringify(ast) === JSON.stringify(ast2) };
}

const cases = [
  "[[\\h:blue:purple| *是* ** *的* ** ]]",
  "[[\\h:blue:purple|*是* ***的***]]",
  "** *的* **",
  "***的***",
];

for (const c of cases) {
  const r = roundTrip(c);
  console.log("SRC:", JSON.stringify(c));
  console.log("AST1:", JSON.stringify(r.ast));
  console.log("GEN1:", JSON.stringify(r.gen1));
  console.log("GEN2:", JSON.stringify(r.gen2));
  console.log("STABLE:", r.stable);
  console.log("---");
}

