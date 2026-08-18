// 临时测试：验证 highlight 内强调的解析
global.window = global;
require("./src/memoria/ui/static/m0/js/ast.js");
require("./src/memoria/ui/static/m0/js/lexer.js");
require("./src/memoria/ui/static/m0/js/parser.js");
const Lexer = global.MemoriaLexer;
const Parser = global.MemoriaParser;

function run(src) {
  const toks = Lexer.tokenize(src);
  const inline = Parser.parseInline(toks);
  return JSON.stringify(inline, null, 0);
}

const cases = [
  "[[\\h:blue:purple| *是* ** *的* ** ]]",
  "[[\\h:blue:purple|*是* ***的***]]",
  "[[\\h:blue:purple| ** *的* ** ]]",
  "[[\\h:blue:purple|** *的* **]]",
  "[[\\h:blue:purple| *是* **的** ]]",
];

for (const c of cases) {
  console.log("SRC:", JSON.stringify(c));
  console.log("AST:", run(c));
  console.log("---");
}
