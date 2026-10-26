"""核实：agent 是否真的能读链接/图谱数据（决定宣传断言是否成立）。"""
import io
import os
import re

AGENT = r"D:\AAA_Jupyter\Memoria\src\memoria\services\agent"

print("=" * 68)
print("① agent 工具注册（找工具名清单）")
print("=" * 68)
tool_pat = re.compile(r'"(read_document|search_documents|resolve_link\w*|graph\w*|get_graph\w*|'
                      r'list_backlinks|kb_\w+|review_\w+)"')
found_names = set()
for root, _d, files in os.walk(AGENT):
    for f in files:
        if not f.endswith(".py"):
            continue
        p = os.path.join(root, f)
        try:
            txt = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in tool_pat.findall(txt):
            found_names.add((m, os.path.relpath(p, AGENT)))
for name, path in sorted(found_names):
    print("   %-24s %s" % (name, path))
if not found_names:
    print("   （无命中）")

print()
print("=" * 68)
print("② agent 侧是否读取链接/图谱数据")
print("=" * 68)
kw = re.compile(r"resolve_link|graph_data|collect_graph|backlink|linked_by|"
                r"outgoing_link|edges\b|sidecar.*link|links\b")
hits = []
for root, _d, files in os.walk(AGENT):
    for f in files:
        if not f.endswith(".py"):
            continue
        p = os.path.join(root, f)
        try:
            txt = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for i, line in enumerate(txt.split("\n"), 1):
            if kw.search(line):
                hits.append((os.path.relpath(p, AGENT), i, line.strip()[:100]))
print("   命中 %d 处" % len(hits))
for h in hits[:15]:
    print("   %s:%d  %s" % h)

print()
print("=" * 68)
print("③ 本体裁决原文（边是否服务 agent）")
print("=" * 68)
onto = r"D:\AAA_Jupyter\Memoria\docs\design\kg-ontology-v0.md"
txt = io.open(onto, encoding="utf-8").read()
for i, line in enumerate(txt.split("\n"), 1):
    if "agent" in line:
        print("   L%d: %s" % (i, line.strip()[:110]))

print()
print("=" * 68)
print("④ 前端 RPC resolve_links 是否只有 UI 用（不供 agent）")
print("=" * 68)
api = r"D:\AAA_Jupyter\Memoria\src\memoria\presentation\api\ui.py"
txt = io.open(api, encoding="utf-8", errors="replace").read()
for i, line in enumerate(txt.split("\n"), 1):
    if "resolve_link" in line:
        print("   ui.py:%d  %s" % (i, line.strip()[:110]))
