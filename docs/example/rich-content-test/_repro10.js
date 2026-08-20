// 笔刷覆盖复现 v10 — PART1: 初始化 + 打开 test-content.md + 切预览
(async function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const out = { log: [] };
  try {
    if (window.MemoriaBridge && window.pywebview && window.pywebview.api) {
      window.MemoriaBridge.installApi(window.pywebview.api);
      out.log.push("api installed");
    } else {
      out.log.push("bridge missing");
    }
    for (let i = 0; i < 40; i++) {
      await sleep(400);
      if (document.querySelectorAll("#file-tree .m0-tree-item").length) break;
    }
    let opened = false;
    document.querySelectorAll("#file-tree .m0-tree-item").forEach((el) => {
      if (el.dataset.path === "test-content.md") { el.click(); opened = true; }
    });
    out.log.push("open=" + opened);
    await sleep(2500);
    const vb = document.querySelector('.m0-view-btn[data-view="preview"]');
    if (vb) { vb.click(); out.log.push("view=preview"); }
    await sleep(2500);
    const preview = document.getElementById("preview");
    out.log.push("previewConnected=" + (preview && preview.isConnected));
    out.log.push("previewTextLen=" + (preview ? preview.textContent.length : -1));
  } catch (e) {
    out.error = e && e.stack ? e.stack : String(e);
  }
  return out;
})()
