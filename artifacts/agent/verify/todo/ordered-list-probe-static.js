// task-157 只读静态调查：start 字段 / 往返 / 调用链
"use strict";
const fs=require("fs"),path=require("path"),vm=require("vm");
const JS=path.join(__dirname,"..","..","..","..","src","memoria","ui","static","app","js");
global.window=global;
for(const f of ["ast.js","lexer.js","parser.js","source-gen.js","mapper.js"]){vm.runInThisContext(fs.readFileSync(path.join(JS,f),"utf8"),{filename:f});}
const P=global.MemoriaParser,G=global.MemoriaSourceGen,M=global.MemoriaMapper;
const j=JSON.stringify;
console.log("=== ③ AST 是否存 start ===");
for(const src of ["10. ten\n11. eleven","3. three\n4. four","1. one\n2. two","- a\n- b","> 10. ten\n> 11. eleven"]){
  const doc=P.parse(src);
  const b=doc.blocks[0];
  const list=b.type==="list"?b:(b.type==="blockquote"&&b.children?(b.children.find(c=>c.type==="list")||null):null);
  console.log(j(src)+"  -> blockType="+b.type+"  list.start="+(list?j(list.start):"n/a")+"  items="+(list?list.items.length:"n/a")+"  block.srcLine="+b.srcLine);
}
console.log("\n=== ①/④ 往返（start>1 是否被重编号；含引用/嵌套/大数字）===");
const SAMPLES=["10. ten\n11. eleven\n","3. three\n4. four\n","9. nine\n10. ten\n","1. one\n2. two\n","- a\n- b\n","> 10. ten\n> 11. eleven\n","> 3. three\n> 4. four\n","5. five\n   - sub a\n   - sub b\n6. six\n","99. big\n100. bigger\n","- a\n10. ten\n"];
for(const s of SAMPLES){const g=G.generate(P.parse(s));console.log((g===s?"OK  ":"CHG ")+j(s)+" -> "+j(g));}
