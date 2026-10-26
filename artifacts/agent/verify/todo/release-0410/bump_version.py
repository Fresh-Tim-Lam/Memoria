"""0.4.10 版本号 bump（L4 版本文件；按人的长期授权「设计→实现→发版不需逐步请示」执行）。

三处：src/memoria/__version__.py（唯一事实源）/ Package/VERSION / docs/conventions/version.md §1
幂等：已是 0.4.10 则跳过。
"""
import io
import os
import re
import sys

ROOT = r"D:\AAA_Jupyter\Memoria"
OLD, NEW = "0.4.9", "0.4.10"


def patch(path, transform, label):
    p = os.path.join(ROOT, path)
    src = io.open(p, encoding="utf-8", newline="").read()
    if NEW in src and OLD not in src:
        print("  SKIP（已是 %s）%s" % (NEW, label))
        return
    out = transform(src)
    if out == src:
        sys.exit("ABORT: 未改动 " + label)
    io.open(p, "w", encoding="utf-8", newline="").write(out)
    print("  OK", label)


# ① 唯一事实源
def t_ver(s):
    if OLD not in s:
        sys.exit("ABORT: __version__.py 里没有 " + OLD)
    return s.replace('__version__ = "%s"' % OLD, '__version__ = "%s"' % NEW, 1)


patch("src/memoria/__version__.py", t_ver, "__version__.py")


# ② Package/VERSION（构建会重写，但先保持一致避免门禁误判）
def t_pkgver(s):
    return re.sub(r"^%s\s*$" % re.escape(OLD), NEW, s, count=1, flags=re.MULTILINE)


patch("Package/VERSION", t_pkgver, "Package/VERSION")


# ③ version.md §1（当前版本行 + 说明行）——说明里的"最近已发布"由发布后 0c 再校验
def t_doc(s):
    s2 = s.replace("| 当前版本 | **%s** |" % OLD, "| 当前版本 | **%s** |" % NEW, 1)
    if s2 == s:
        sys.exit("ABORT: version.md 当前版本行未命中")
    return s2


patch("docs/conventions/version.md", t_doc, "version.md §1 当前版本")

print()
print("复核：")
for path in ("src/memoria/__version__.py", "Package/VERSION", "docs/conventions/version.md"):
    p = os.path.join(ROOT, path)
    txt = io.open(p, encoding="utf-8", errors="replace").read()
    print("  %-32s 0.4.10=%d  0.4.9=%d" % (path, txt.count(NEW), txt.count(OLD)))
