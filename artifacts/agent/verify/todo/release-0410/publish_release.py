"""发布 GitHub Release v0.4.10 并上传两个 canonical 资产。

- 标题严格 `Memoria v0.4.10`；body 来自 artifacts/release-body-v0.4.10.md（EN 在前/ZH 在后/造价段）
- 资产：Memoria-v0.4.10-win64.zip（full）、Memoria-v0.4.10-win64-lite.zip（lite）
- 幂等：若 release 已存在则复用；同名资产已存在则跳过（并报告其 size/sha 对照）
- 只读 token 从 GH_TOKEN 文件读，不打印
"""
import hashlib
import io
import json
import os
import sys
import time
import urllib.request

ROOT = r"D:\AAA_Jupyter\Memoria"
API = "https://api.github.com/repos/Fresh-Tim-Lam/Memoria"
TAG = "v0.4.10"
TITLE = "Memoria v0.4.10"
BODY_FILE = os.path.join(ROOT, "artifacts", "release-body-v0.4.10.md")
DIST = os.path.join(ROOT, "dist-release", "v0.4.10")
ASSETS = [
    ("Memoria-v0.4.10-win64-lite.zip", os.path.join(DIST, "Memoria-v0.4.10-win64-lite.zip")),
    ("Memoria-v0.4.10-win64.zip", os.path.join(DIST, "Memoria-v0.4.10-win64.zip")),
]

TOKEN = io.open(os.path.join(ROOT, "GH_TOKEN"), encoding="utf-8").read().strip()
HEADERS = {
    "Authorization": "Bearer " + TOKEN,
    "Accept": "application/vnd.github+json",
    "User-Agent": "memoria-release",
    "X-GitHub-Api-Version": "2022-11-28",
}


def req(url, *, method="GET", data=None, headers=None, timeout=120):
    h = dict(HEADERS)
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    return urllib.request.urlopen(r, timeout=timeout)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


print("=" * 70)
print("① 读取 body 并做最简自检")
print("=" * 70)
body = io.open(BODY_FILE, encoding="utf-8").read()
assert body.lstrip().startswith("# Memoria v0.4.10"), "body 标题不符"
assert "## English" in body and ("## 中文" in body or "## Chinese" in body), "body 缺双语段"
print("  body %d 字节；标题/双语段 OK" % len(body))

print()
print("=" * 70)
print("② 创建或复用 Release")
print("=" * 70)
release = None
try:
    with req("%s/releases/tags/%s" % (API, TAG)) as r:
        release = json.load(r)
    print("  已存在 release id=%s（复用）" % release["id"])
except urllib.error.HTTPError as e:
    if e.code != 404:
        raise
    payload = json.dumps({
        "tag_name": TAG, "name": TITLE, "body": body,
        "draft": False, "prerelease": False,
    }).encode("utf-8")
    with req(API + "/releases", method="POST", data=payload) as r:
        release = json.load(r)
    print("  已创建 release id=%s" % release["id"])

print("  title = %r" % release["name"])
print("  tag   = %s" % release["tag_name"])
existing = {a["name"]: a for a in release.get("assets", [])}

print()
print("=" * 70)
print("③ 上传资产")
print("=" * 70)
results = []
for name, path in ASSETS:
    if not os.path.isfile(path):
        sys.exit("ABORT: 缺资产 " + path)
    size = os.path.getsize(path)
    if name in existing:
        a = existing[name]
        print("  [SKIP] %s 已存在：远端 %d 字节 / 本地 %d 字节%s"
              % (name, a["size"], size, "" if a["size"] == size else "  ⚠️ 大小不一致"))
        results.append((name, a["size"], a.get("browser_download_url")))
        continue
    print("  [UP  ] %s  %.1f MB  计算 sha256..." % (name, size / 1048576))
    local_sha = sha256_of(path)
    # 资产上传必须走 uploads.github.com（api.github.com 的同一路径对 POST 返回 404）
    url = "https://uploads.github.com/repos/Fresh-Tim-Lam/Memoria/releases/%s/assets?name=%s" % (
        release["id"], urllib.parse.quote(name))
    with open(path, "rb") as f:
        t0 = time.time()
        with req(url, method="POST", data=f,
                 headers={"Content-Type": "application/zip",
                          "Content-Length": str(size)},
                 timeout=3600) as r:
            a = json.load(r)
    print("  [DONE] %s  id=%s  %d 字节  用时 %.1fs" % (name, a["id"], a["size"], time.time() - t0))
    print("         本地 sha256 = %s" % local_sha)
    results.append((name, a["size"], a.get("browser_download_url")))

print()
print("=" * 70)
print("④ 复核远端 Release 状态")
print("=" * 70)
with req("%s/releases/tags/%s" % (API, TAG)) as r:
    final = json.load(r)
print("  name  = %r" % final["name"])
print("  draft = %s  prerelease = %s" % (final["draft"], final["prerelease"]))
print("  html  = %s" % final["html_url"])
for a in final.get("assets", []):
    print("  asset: %-36s %10.1f MB" % (a["name"], a["size"] / 1048576))
print()
print("RESULT: OK")
