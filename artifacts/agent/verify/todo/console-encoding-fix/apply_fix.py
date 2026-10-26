"""修"控制台编码导致假红"：把 CLI 输出的非 ASCII 标记换成 ASCII，并强制 stdout/stderr UTF-8。

为什么必须修（不是洁癖）：
    docs-consistency 首次跑 pytest 出现 1 failed —— UnicodeEncodeError: cp1252 can't encode '\u2713'
    源头是 packaging/make_release_zip.py 打印 '✓'
    ⇒ 发版门禁若在 cp1252 控制台（Windows 旧代码页 / CI 默认）跑，就会【假红】。
    ⇒ 假红比不检查更糟：会让人开始不信门禁，或者绕过它。

修法（双保险）：
    ① 输出去掉非 ASCII 标记（✓/✗ ⇒ [OK]/[FAIL]）
    ② 入口处 reconfigure stdout/stderr 为 UTF-8（errors="replace"），
       这样即使别处仍有中文，也不会因编码崩掉
"""
import io
import os
import re
import sys

ROOT = r"D:\AAA_Jupyter\Memoria"
TARGETS = [
    os.path.join(ROOT, "packaging", "make_release_zip.py"),
    os.path.join(ROOT, "scripts", "agent", "release_format_gate.py"),
    os.path.join(ROOT, "scripts", "agent", "release_manifest.py"),
]

# 只替换【输出标记】用途的字符，不碰中文正文
REPL = [
    ('print(f"  ✗ {item}", file=sys.stderr)', 'print(f"  [FAIL] {item}", file=sys.stderr)'),
    ('print(f"✓ ', 'print(f"[OK] '),
    ('print(f"✗ ', 'print(f"[FAIL] '),
]


def ensure_utf8_stdout(src, path):
    if "def _force_utf8_stdio" in src:
        return src, False
    helper = '''
def _force_utf8_stdio():
    """Windows 旧代码页（cp1252/cp936）下 print 非 ASCII 会 UnicodeEncodeError ⇒ 假红。
    统一把 stdout/stderr 设为 UTF-8（errors=replace），保证门禁不会因为控制台编码崩掉。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_force_utf8_stdio()
'''
    # 插到最后一个顶层 import 之后
    lines = src.split("\n")
    last_import = 0
    for i, line in enumerate(lines):
        if re.match(r"^(import|from)\s", line):
            last_import = i
    lines.insert(last_import + 1, helper)
    return "\n".join(lines), True


for path in TARGETS:
    if not os.path.isfile(path):
        print("  SKIP 不存在:", path)
        continue
    src = io.open(path, encoding="utf-8", newline="").read()
    before = src
    for old, new in REPL:
        if old in src:
            src = src.replace(old, new)
    src, added = ensure_utf8_stdout(src, path)
    if src != before:
        io.open(path, "w", encoding="utf-8", newline="").write(src)
        print("  PATCHED %s（utf8 helper=%s）" % (os.path.basename(path), added))
    else:
        print("  unchanged %s" % os.path.basename(path))

# 复核：这些文件里 print 的非 ASCII 标记应为 0
print()
print("复核（print 里的 ✓/✗ 残留）：")
bad = 0
for path in TARGETS:
    if not os.path.isfile(path):
        continue
    txt = io.open(path, encoding="utf-8", errors="replace").read()
    for i, line in enumerate(txt.split("\n"), 1):
        if "print(" in line and re.search(r"[✓✗✔✘✅❌]", line):
            print("  ⚠️ %s:%d  %s" % (os.path.basename(path), i, line.strip()[:80]))
            bad += 1
print("  残留 %d 处" % bad)
