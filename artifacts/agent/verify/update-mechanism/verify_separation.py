"""验证：自动更新替换应用文件夹是否会丢用户数据（只读排查）。"""
import io
import json
import os
import re

PKG = r"D:\AAA_Jupyter\Memoria\Package"
LOCAL = os.path.join(os.environ["LOCALAPPDATA"], "Memoria")
KB = r"D:\AAA_Jupyter\Memoria\docs\example\AAA_Vocab"

print("=" * 70)
print("① 应用文件夹（Package/）里有什么 —— 顶层")
print("=" * 70)
if os.path.isdir(PKG):
    total = 0
    for name in sorted(os.listdir(PKG))[:30]:
        p = os.path.join(PKG, name)
        if os.path.isdir(p):
            sz = sum(os.path.getsize(os.path.join(r, f))
                     for r, _d, fs in os.walk(p) for f in fs
                     if os.path.exists(os.path.join(r, f)))
            print("   [dir ] %-28s %8.1f MB" % (name, sz / 1048576))
        else:
            sz = os.path.getsize(p)
            total += sz
            print("   [file] %-28s %8.1f MB" % (name, sz / 1048576))
else:
    print("   Package 不存在")

print()
print("=" * 70)
print("② 用户态目录（%LOCALAPPDATA%/Memoria）—— 应用外置的配置")
print("=" * 70)
if os.path.isdir(LOCAL):
    for r, _d, fs in os.walk(LOCAL):
        for f in fs:
            p = os.path.join(r, f)
            rel = os.path.relpath(p, LOCAL)
            print("   %-46s %7.1f KB" % (rel, os.path.getsize(p) / 1024))
else:
    print("   不存在")

print()
print("=" * 70)
print("③ 知识库（AAA_Vocab）里用户的重要本地数据")
print("=" * 70)
for sub in [".memoria/agent/sessions", ".memoria/agent/review", ".memoria/build", ".memoria/cache"]:
    d = os.path.join(KB, *sub.split("/"))
    if os.path.isdir(d):
        n = sum(1 for _r, _d2, fs in os.walk(d) for _ in fs)
        sz = sum(os.path.getsize(os.path.join(r, f)) for r, _d2, fs in os.walk(d) for f in fs)
        print("   %-30s %4d 文件  %7.1f MB" % (sub, n, sz / 1048576))
    else:
        print("   %-30s (不存在)" % sub)

print()
print("=" * 70)
print("④ 关键问题：应用是否往【安装目录】里写用户数据？")
print("=" * 70)
# 检查代码里是否有往 install_root 写配置/日志的路径
SRC = r"D:\AAA_Jupyter\Memoria\src\memoria"
patterns = [
    r"install_root\(\)\s*/\s*[\"'](config|logs|data|user)",
    r"Path\.home\(\)|expanduser",
]
hits = []
for r, _d, fs in os.walk(SRC):
    for f in fs:
        if not f.endswith(".py"):
            continue
        p = os.path.join(r, f)
        try:
            txt = io.open(p, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for pat in patterns:
            for m in re.finditer(pat, txt):
                ln = txt[:m.start()].count("\n") + 1
                hits.append((os.path.relpath(p, SRC), ln, pat))
for h in hits[:12]:
    print("   %s:%d  %s" % h)
if not hits:
    print("   无 install_root 下的 config/logs/data 写入点")

print()
print("=" * 70)
print("⑤ Package/config 是否还有活的配置（旧的安装内配置）")
print("=" * 70)
pc = os.path.join(PKG, "config")
if os.path.isdir(pc):
    for f in sorted(os.listdir(pc)):
        p = os.path.join(pc, f)
        if os.path.isfile(p):
            print("   %-24s %6.1f KB  mtime=%s" % (
                f, os.path.getsize(p) / 1024,
                __import__("datetime").datetime.fromtimestamp(os.path.getmtime(p)).strftime("%m-%d %H:%M")))
else:
    print("   不存在")
