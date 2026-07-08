(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const api = () => window.pywebview && window.pywebview.api;

  let state = {
    kbPath: "",
    files: [],
    currentPath: null,
    doc: null,
    activeKpId: null,
    assist: null,
  };

  function setStatus(msg, stats) {
    $("#status-info").textContent = msg;
    if (stats !== undefined) $("#status-stats").textContent = stats;
  }

  function showWelcome(show) {
    $("#welcome").classList.toggle("hidden", !show);
    $("#editor-wrap").classList.toggle("hidden", show);
  }

  async function call(fn, ...args) {
    const a = api();
    if (!a || !a[fn]) throw new Error("API 不可用: " + fn);
    return await a[fn](...args);
  }

  async function initKb() {
    try {
      state.kbPath = await call("get_kb_path");
      if (state.kbPath) {
        $("#kb-indicator").textContent = state.kbPath;
        $("#kb-indicator").classList.remove("hidden");
        await refreshFiles();
        setStatus("已加载知识库", state.kbPath);
        const preferred = state.files.find((f) => f.path === "mdp.md") || state.files[0];
        if (preferred) await openFile(preferred.path);
      }
    } catch (e) {
      setStatus("等待后端…");
    }
  }

  async function openKb() {
    const path = await call("select_directory");
    if (!path) return;
    state.kbPath = path;
    $("#kb-indicator").textContent = path;
    $("#kb-indicator").classList.remove("hidden");
    await refreshFiles();
    setStatus("已打开知识库", path);
  }

  async function refreshFiles() {
    const res = await call("list_files");
    if (res.status !== "ok") {
      setStatus(res.message || "列表失败");
      return;
    }
    state.files = res.files || [];
    renderFileTree();
  }

  function renderFileTree() {
    const el = $("#file-tree");
    if (!state.files.length) {
      el.innerHTML = '<div class="empty">无 Markdown 文件</div>';
      return;
    }
    el.innerHTML = state.files
      .map((f) => {
        const active = f.path === state.currentPath ? " active" : "";
        const side = f.has_sidecar ? "" : " no-sidecar";
        const icon = f.has_sidecar ? "📄" : "📝";
        return `<div class="m0-tree-item${active}${side}" data-path="${esc(f.path)}" title="${esc(f.path)}">
          <span class="m0-tree-icon">${icon}</span>
          <span class="m0-tree-label">${esc(basename(f.path))}</span>
        </div>`;
      })
      .join("");

    el.querySelectorAll(".m0-tree-item").forEach((node) => {
      node.addEventListener("click", () => openFile(node.dataset.path));
    });
  }

  function renderTabs() {
    const tabs = $("#tabs");
    if (!state.currentPath) {
      tabs.innerHTML = "";
      return;
    }
    tabs.innerHTML = `<div class="tab active"><span>${esc(basename(state.currentPath))}</span></div>`;
  }

  async function openFile(relPath) {
    setStatus("加载中…", relPath);
    const res = await call("load_document", relPath);
    if (res.status !== "ok") {
      setStatus(res.message || "加载失败");
      return;
    }
    state.currentPath = relPath;
    state.doc = res;
    state.activeKpId = null;
    showWelcome(false);
    renderFileTree();
    renderTabs();
    renderEditor(res);
    renderKpList(res);
    renderProposals(res);
    setStatus(
      relPath,
      `${res.knowledge_points.length} KP · ${res.lines.length} 行`
    );
  }

  function renderEditor(doc) {
    $("#file-title").textContent = doc.path;
    const desc = (doc.sidecar && doc.sidecar.description) || "";
    $("#file-meta").textContent = desc;

    const editor = $("#editor");
    editor.innerHTML = doc.lines
      .map((line, i) => {
        const n = i + 1;
        return `<div class="m0-line" data-line="${n}" id="line-${n}">
          <span class="m0-lineno">${n}</span>
          <span class="m0-line-content">${esc(line)}</span>
        </div>`;
      })
      .join("");
  }

  function renderKpList(doc) {
    const el = $("#kp-list");
    const kps = doc.knowledge_points || [];
    $("#kp-count").textContent = kps.length ? `${kps.length}` : "";

    if (!kps.length && !(doc.heading_proposals || []).length) {
      el.innerHTML = '<div class="empty">无知识点</div>';
      return;
    }
    if (!kps.length) {
      el.innerHTML = '<div class="empty">可从标题生成提议</div>';
      return;
    }

    el.innerHTML = kps
      .map((kp) => {
        const rr = kp.range_resolved || {};
        let cls = "m0-kp-item";
        if (kp.id === state.activeKpId) cls += " active";
        let meta = kp.id;
        if (rr.ok) {
          meta = `L${rr.start_line}–${rr.end_line}`;
        } else if (rr.error) {
          cls += rr.error.includes("not_found") ? " error" : " warn";
          meta = errorLabel(rr.error);
        }
        const tags = (kp.tags || [])
          .map((t) => `<span class="m0-tag">${esc(t)}</span>`)
          .join("");
        return `<div class="${cls}" data-kp="${esc(kp.id)}">
          <div class="m0-kp-name">${esc(kp.name || kp.id)}</div>
          <div class="m0-kp-meta"><span>${esc(meta)}</span>${tags}</div>
        </div>`;
      })
      .join("");

    el.querySelectorAll(".m0-kp-item").forEach((node) => {
      node.addEventListener("click", () => onKpClick(node.dataset.kp));
    });
  }

  function renderProposals(doc) {
    const banner = $("#proposal-banner");
    const proposals = doc.heading_proposals || [];
    if (!proposals.length || (doc.knowledge_points || []).length) {
      banner.classList.add("hidden");
      banner.innerHTML = "";
      return;
    }
    banner.classList.remove("hidden");
    banner.innerHTML =
      `<span>检测到 ${proposals.length} 个标题，可生成 range 提议：</span>` +
      proposals
        .map(
          (p, i) =>
            `<span class="proposal-chip" data-idx="${i}">${esc(p.name)}</span>`
        )
        .join("");

    banner.querySelectorAll(".proposal-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const p = proposals[+chip.dataset.idx];
        openAssistForProposal(p);
      });
    });
  }

  function errorLabel(err) {
    const map = {
      start_snippet_not_found: "起点未找到",
      end_snippet_not_found: "终点未找到",
      end_before_start: "终点在起点前",
      missing_snippet: "缺少 snippet",
    };
    return map[err] || err;
  }

  function onKpClick(kpId) {
    const kp = (state.doc.knowledge_points || []).find((k) => k.id === kpId);
    if (!kp) return;
    state.activeKpId = kpId;
    renderKpList(state.doc);

    const rr = kp.range_resolved || {};
    if (rr.ok) {
      highlightRange(rr.start_line, rr.end_line);
      return;
    }
    openAssistForKp(kp);
  }

  function clearHighlights() {
    document.querySelectorAll(".m0-line").forEach((el) => {
      el.classList.remove("kp-highlight-flash", "fade-out", "in-range");
    });
  }

  function highlightRange(startLine, endLine) {
    clearHighlights();
    for (let n = startLine; n <= endLine; n++) {
      const line = document.getElementById("line-" + n);
      if (line) {
        line.classList.add("in-range", "kp-highlight-flash");
        if (n === startLine) {
          line.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      }
    }
    window.setTimeout(() => {
      document.querySelectorAll(".m0-line.kp-highlight-flash").forEach((el) => {
        el.classList.add("fade-out");
      });
    }, 800);
    window.setTimeout(() => clearHighlights(), 2500);
  }

  function openAssistForKp(kp) {
    const rr = kp.range_resolved || {};
    state.assist = {
      mode: "kp",
      kpId: kp.id,
      name: kp.name || kp.id,
      startLine: rr.start_line || kp.range?.start?.line_hint || 1,
      endLine: rr.end_line || kp.range?.end?.line_hint || 1,
      error: rr.error,
      startCandidates: rr.start_candidates || [],
      endCandidates: rr.end_candidates || [],
    };
    showAssistModal();
  }

  function openAssistForProposal(proposal) {
    const r = proposal.range || {};
    state.assist = {
      mode: "proposal",
      kpId: slugify(proposal.name),
      name: proposal.name,
      startLine: r.start?.line_hint || 1,
      endLine: r.end?.line_hint || 1,
      error: null,
      startCandidates: [],
      endCandidates: [],
    };
    showAssistModal();
  }

  function showAssistModal() {
    const a = state.assist;
    if (!a) return;
    $("#assist-title").textContent =
      a.mode === "proposal" ? "确认标题 range" : "定位辅助 — " + a.name;

    let html = "";
    if (a.error) {
      html += `<p style="color:var(--error);margin-bottom:8px">${esc(errorLabel(a.error))}</p>`;
    }
    html += `<p>起点行 <input type="number" id="assist-start" min="1" value="${a.startLine}" style="width:64px;background:var(--bg-primary);color:var(--text-primary);border:1px solid var(--border);padding:2px 4px;"> 
      终点行 <input type="number" id="assist-end" min="1" value="${a.endLine}" style="width:64px;background:var(--bg-primary);color:var(--text-primary);border:1px solid var(--border);padding:2px 4px;"></p>`;

    if (a.startCandidates.length > 1) {
      html += `<p><strong>起点候选</strong></p>`;
      html += renderCandidates("start", a.startCandidates);
    }
    if (a.endCandidates.length > 1) {
      html += `<p><strong>终点候选</strong></p>`;
      html += renderCandidates("end", a.endCandidates);
    }

    html += `<p class="m0-muted">可在编辑器中查看行号，或从候选中选择。</p>`;
    $("#assist-body").innerHTML = html;
    $("#assist-modal").classList.remove("hidden");

    $("#assist-body").querySelectorAll('input[type="radio"]').forEach((inp) => {
      inp.addEventListener("change", () => {
        const which = inp.name.replace("assist-", "");
        const line = +inp.value;
        if (which === "start") $("#assist-start").value = line;
        else $("#assist-end").value = line;
      });
    });
  }

  function renderCandidates(which, indices) {
    const lines = state.doc.lines;
    return indices
      .map((i) => {
        const n = i + 1;
        const text = (lines[i] || "").trim().slice(0, 72);
        return `<div class="candidate-row">
          <input type="radio" name="assist-${which}" value="${n}" id="c-${which}-${n}">
          <label for="c-${which}-${n}" class="candidate-line"><span class="m0-muted">L${n}</span> ${esc(text)}</label>
        </div>`;
      })
      .join("");
  }

  function closeAssist() {
    $("#assist-modal").classList.add("hidden");
    state.assist = null;
  }

  async function confirmAssist() {
    if (!state.assist || !state.currentPath) return;
    const start = +$("#assist-start").value;
    const end = +$("#assist-end").value;
    const a = state.assist;
    closeAssist();
    setStatus("写入侧车…");
    const res = await call(
      "confirm_kp_range",
      state.currentPath,
      a.kpId,
      a.name,
      start,
      end
    );
    if (res.status !== "ok") {
      setStatus(res.message || "写入失败");
      return;
    }
    state.doc = res;
    renderEditor(res);
    renderKpList(res);
    renderProposals(res);
    renderFileTree();
    onKpClick(a.kpId);
    setStatus("已更新 range", `${a.kpId} L${start}–${end}`);
  }

  function setupSidebarResize() {
    const sidebar = $("#m0-sidebar");
    const resizer = $("#sidebar-resizer");
    let dragging = false;
    resizer.addEventListener("mousedown", (e) => {
      dragging = true;
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const w = Math.max(180, Math.min(480, e.clientX));
      sidebar.style.width = w + "px";
    });
    window.addEventListener("mouseup", () => {
      dragging = false;
    });
  }

  function esc(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function basename(p) {
    const parts = p.replace(/\\/g, "/").split("/");
    return parts[parts.length - 1];
  }

  function slugify(name) {
    return name
      .toLowerCase()
      .replace(/[^\w\u4e00-\u9fff]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 40) || "kp";
  }

  function bindEvents() {
    $("#btn-open").addEventListener("click", openKb);
    $("#btn-welcome-open").addEventListener("click", openKb);
    $("#btn-refresh").addEventListener("click", async () => {
      await refreshFiles();
      if (state.currentPath) await openFile(state.currentPath);
    });
    $("#assist-close").addEventListener("click", closeAssist);
    $("#assist-cancel").addEventListener("click", closeAssist);
    $(".m0-modal-backdrop").addEventListener("click", closeAssist);
    $("#assist-confirm").addEventListener("click", confirmAssist);
    setupSidebarResize();
  }

  window.addEventListener("pywebviewready", () => {
    bindEvents();
    initKb();
  });

  if (window.pywebview) {
    bindEvents();
    initKb();
  }
})();
