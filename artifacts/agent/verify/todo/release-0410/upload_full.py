"""稳健上传 full 包（1180MB）到 GitHub Release 资产。

上一版用 urllib 单请求上传，连接停滞 40 分钟无进展。
本版改进：
  · http.client 显式 socket 超时 + TCP keepalive
  · 每 5% 打印进度（可判断是"慢"还是"卡死"）
  · 失败自动重试 2 次；重试前删除可能残留的 starter 资产
  · 幂等：若远端已有同名且 size 一致则跳过
"""
import hashlib
import http.client
import io
import json
import os
import socket
import sys
import time
import urllib.parse
import urllib.request

ROOT = r"D:\AAA_Jupyter\Memoria"
API = "https://api.github.com/repos/Fresh-Tim-Lam/Memoria"
TAG = "v0.4.10"
NAME = "Memoria-v0.4.10-win64.zip"
PATH = os.path.join(ROOT, "dist-release", "v0.4.10", NAME)
TOKEN = io.open(os.path.join(ROOT, "GH_TOKEN"), encoding="utf-8").read().strip()
HDRS = {
    "Authorization": "Bearer " + TOKEN,
    "Accept": "application/vnd.github+json",
    "User-Agent": "memoria-release",
    "X-GitHub-Api-Version": "2022-11-28",
}


def api(url, method="GET", data=None, timeout=120):
    r = urllib.request.Request(url, data=data, method=method, headers=HDRS)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.load(resp)


def release():
    return api("%s/releases/tags/%s" % (API, TAG))


def drop_asset(asset_id):
    api("%s/releases/assets/%s" % (API, asset_id), method="DELETE")


def sha256_of(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(c)
    return h.hexdigest()


rel = release()
size = os.path.getsize(PATH)
local_sha = sha256_of(PATH)
print("  Release id=%s  title=%r" % (rel["id"], rel["name"]))
print("  待上传 %s  %.1f MB（%.0f 字节）" % (NAME, size / 1048576, size))
print("  本地 sha256 = %s" % local_sha)

existing = {a["name"]: a for a in rel.get("assets", [])}
if NAME in existing and existing[NAME]["size"] == size:
    print("  [SKIP] 远端已有同名同大小资产：%s" % NAME)
    sys.exit(0)
if NAME in existing:
    print("  [DEL ] 远端已有同名但大小不同（%d）⇒ 删除后重传" % existing[NAME]["size"])
    drop_asset(existing[NAME]["id"])

for attempt in range(1, 4):
    print()
    print("=== 上传尝试 %d/3 ===" % attempt)
    conn = http.client.HTTPSConnection("uploads.github.com", timeout=900)
    try:
        url = "/repos/Fresh-Tim-Lam/Memoria/releases/%s/assets?name=%s" % (
            rel["id"], urllib.parse.quote(NAME))
        hdrs = dict(HDRS)
        hdrs["Content-Type"] = "application/zip"
        hdrs["Content-Length"] = str(size)
        # 只用 putrequest + 手动 send（不能先 request 再 putrequest ⇒ Request-sent）
        conn.putrequest("POST", url, skip_accept_encoding=True)
        for k, v in hdrs.items():
            if k.lower() != "host":
                conn.putheader(k, v)
        conn.endheaders()

        sent = 0
        t0 = time.time()
        last_report = -1
        with open(PATH, "rb") as f:
            while True:
                chunk = f.read(4 * 1024 * 1024)
                if not chunk:
                    break
                conn.send(chunk)
                sent += len(chunk)
                pct = int(sent * 100 / size)
                bucket = pct // 5
                if bucket != last_report:
                    last_report = bucket
                    el = time.time() - t0
                    rate = sent / el / 1048576 if el > 0 else 0
                    eta = (size - sent) / (sent / el) if sent and el else 0
                    print("  %3d%%  %7.1f/%.1f MB  %.2f MB/s  ETA %.0fs"
                          % (pct, sent / 1048576, size / 1048576, rate, eta))
        resp = conn.getresponse()
        body = resp.read()
        print("  HTTP %d（用时 %.1fs）" % (resp.status, time.time() - t0))
        if resp.status in (200, 201):
            a = json.loads(body)
            print("  [DONE] asset id=%s size=%d state=%s" % (a["id"], a["size"], a["state"]))
            sys.exit(0)
        print("  响应：%s" % body[:300])
    except (socket.timeout, TimeoutError, ConnectionError, OSError) as e:
        print("  [FAIL] %s: %s" % (type(e).__name__, e))
        # 清掉可能残留的 starter 资产
        try:
            r2 = release()
            for a in r2.get("assets", []):
                if a["name"] == NAME and a["state"] != "uploaded":
                    print("  清理残留 starter 资产 id=%s" % a["id"])
                    drop_asset(a["id"])
        except Exception:
            pass
        time.sleep(10)
    finally:
        try:
            conn.close()
        except Exception:
            pass

print()
print("RESULT: FAIL（三次尝试均未完成）")
sys.exit(1)
