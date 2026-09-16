/**
 * mermaid-theme.js — Mermaid（v11）统一主题
 *
 * 依据：docs/conventions/frontend-modules.md（R1 新代码不进 app.js / R2 由使用方调用）
 * 接口：MemoriaMermaidTheme.options() → 直接交给 window.mermaid.initialize(...)
 *       MemoriaMermaidTheme.init()    → 幂等初始化
 * 配色：读 :root 上的 --mmd-* 变量（缺省回落到 --bg-* / --text-* / --border*）
 *       → 浅色主题只需覆盖这几个变量，不必改本文件
 * 状态：生效中，2026-09-16
 */
(function () {
  "use strict";

  var H = window.MemoriaMermaidTheme = window.MemoriaMermaidTheme || {};

  /** 读取 :root 上的 CSS 变量（取不到时用兜底值） */
  function v(name, fallback) {
    try {
      var got = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return got || fallback;
    } catch (e) {
      return fallback;
    }
  }

  H.options = function () {
    var bg = v("--bg-primary", "#1e1e1e");
    var panel = v("--mmd-node-bg", v("--bg-tertiary", "#333333"));
    var panel2 = v("--bg-secondary", "#252526");
    var nodeBorder = v("--mmd-node-border", v("--border-light", "#4c4c4c"));
    var nodeText = v("--mmd-node-text", v("--text-primary", "#cccccc"));
    var line = v("--mmd-line", "#9a9a9a");
    var labelBg = v("--mmd-label-bg", bg);
    var labelText = v("--mmd-label-text", nodeText);
    var clusterBg = v("--mmd-cluster-bg", "rgba(255,255,255,0.03)");
    var clusterBorder = v("--mmd-cluster-border", v("--border", "#3c3c3c"));
    var noteBg = v("--mmd-note-bg", panel2);
    var noteBorder = v("--mmd-note-border", nodeBorder);

    return {
      startOnLoad: false,
      securityLevel: "loose",
      // mermaid 默认把语法错误画成一张 "Syntax error" 图；关掉，交给应用统一提示
      suppressErrorRendering: true,
      // base：只有它会完全采用下面的 themeVariables（default/forest/dark 会覆盖一部分）
      theme: "base",
      fontFamily: "inherit",
      themeVariables: {
        darkMode: v("--mmd-dark", "1") === "1",
        background: bg,
        // 节点框体
        primaryColor: panel,
        primaryTextColor: nodeText,
        primaryBorderColor: nodeBorder,
        mainBkg: panel,
        nodeBorder: nodeBorder,
        nodeTextColor: nodeText,
        textColor: nodeText,
        titleColor: v("--text-bright", "#ffffff"),
        // 次级/三级（子图、注释、分区）
        secondaryColor: panel2,
        secondaryTextColor: nodeText,
        secondaryBorderColor: nodeBorder,
        tertiaryColor: bg,
        tertiaryTextColor: nodeText,
        tertiaryBorderColor: clusterBorder,
        clusterBkg: clusterBg,
        clusterBorder: clusterBorder,
        // 连线与连线标签
        lineColor: line,
        edgeLabelBackground: labelBg,
        labelBackground: labelBg,
        labelTextColor: labelText,
        // 时序图
        actorBkg: panel,
        actorBorder: nodeBorder,
        actorTextColor: nodeText,
        signalColor: line,
        signalTextColor: labelText,
        noteBkgColor: noteBg,
        noteBorderColor: noteBorder,
        noteTextColor: nodeText,
        // 类图 / 状态图 / 其它
        classText: nodeText,
        gridColor: clusterBorder,
        todayLineColor: v("--accent", "#007acc"),
        fontSize: "13px",
      },
      // 布局与线型：平滑曲线 + 足够留白，减少折线互相压线
      flowchart: {
        curve: "basis",
        padding: 14,
        nodeSpacing: 42,
        rankSpacing: 48,
        diagramPadding: 6,
        useMaxWidth: true,
        htmlLabels: true,
      },
      sequence: { useMaxWidth: true, actorMargin: 56, messageMargin: 34, mirrorActors: false },
      state: { useMaxWidth: true },
      class: { useMaxWidth: true },
      er: { useMaxWidth: true },
      gantt: { useMaxWidth: true },
    };
  };

  /** 幂等初始化（应用侧调一次即可） */
  H.init = function () {
    if (!window.mermaid || !window.mermaid.initialize) return false;
    window.mermaid.initialize(H.options());
    return true;
  };
})();
