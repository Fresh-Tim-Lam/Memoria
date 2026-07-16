# Debug Session: preview-canvas-lost

**Status**: [OPEN]
**Started**: 2026-07-15
**Session ID**: `preview-canvas-lost`

## Symptom

设置模态框图谱预览区出现两个 canvas 共存，且预览内容丢失（空白）：

- `<canvas class="m0-graph-canvas" width="258" height="462" style="cursor: grab;">` （2D 视图 canvas）
- `<canvas width="258" height="462" style="display: block; width: 258px; height: 462px; cursor: grab;">` （3D 视图 canvas，由 THREE.js setSize 设置 style）

预期：同一时刻预览区只应有一个 canvas（2D 或 3D），且应渲染节点/边内容。

## Reproduction Steps

1. 启动应用，打开设置模态框（齿轮按钮）
2. 默认 tab 为 "2D 图谱" → 预览区显示 2D canvas
3. 切换到 "3D 图谱" tab → 预览区应仅显示 3D canvas
4. 切换回 "2D 图谱" tab → 预览区应仅显示 2D canvas
5. 实际：预览区出现两个 canvas，内容均丢失

## Hypotheses

- **H1 - teardownPreview 未真正清理 DOM**：`teardownPreview()` 调用 `previewView.destroy()`，但 2D 的 `canvas.replaceWith(div)` 与 3D 的 `container.removeChild(canvas)` 在某些时序下未执行（如容器已被替换导致 parentNode 不匹配）。后续 `bodyEl.innerHTML = ...` 重建容器，但旧 canvas 可能通过 ResizeObserver 异步回调或其他路径被重新插入。
  - 观察点：teardownPreview 时 container.childNodes 数量、destroy 调用前后 DOM 状态

- **H2 - bootPreview 异步竞态**：`bootPreview()` 使用 `requestAnimationFrame` 异步轮询容器尺寸（30 次）。用户快速切换 tab 时，旧 bootPreview 闭包持有旧 root 引用，但模块级 `previewView` 已被新 view 替换。旧 bootPreview 触发 `previewView?.reflow?.()` 等方法时，操作的是新 view（不是旧 view），可能让新 view 重复初始化或在错误容器上绘制。
  - 观察点：bootPreview 调用与触发时序、previewView 引用变化

- **H3 - previewView 状态不一致**：`teardownPreview` 中 `if (previewView) previewView.destroy()` 若抛异常（如 WebGL 资源已释放），后续的 `previewEngine/Layout/View = null` 仍会执行（无 try/catch）。但若 destroy 在 2D canvas 替换前抛错，canvas 残留。下次 ensurePreview 创建新 view 时清空 innerHTML 应能清理——除非 previewView 与 previewEngine 状态不同步（一个为 null 一个不为 null）。
  - 观察点：destroy 是否抛异常、previewView/Layout/Engine 三者同步性

- **H4 - 主图谱 onChange 触发外部 view 操作**：`notifyChange()` 调用 `onChangeHandler(getViewOptions())`，若 onChangeHandler 调用主图谱 view 的方法，且主图谱 view 与设置预览共享某些状态（如 SAMPLE_GRAPH 引用），可能间接影响预览。但这不会导致双 canvas。
  - 观察点：onChangeHandler 调用栈

- **H5 - setSettingsTab 重复调用**：若 openModal 在某些情况下被连续调用两次（如 `bindModal` 重复绑定，或外部代码触发），第一次 setSettingsTab 创建 view A，第二次 teardownPreview 销毁 A 创建 view B。如果 A 的 canvas 未被 destroy 清理（destroy 异常或时序问题），则两个 canvas 共存。
  - 观察点：setSettingsTab 调用次数、openModal 调用次数

## Investigation Plan

1. 启动 Debug Server
2. 在以下关键点加入 instrumentation：
   - `teardownPreview` 入口/出口：记录调用栈、destroy 前后 container.childNodes
   - `ensurePreview2d` / `ensurePreview3d`：记录创建分支、container.childNodes
   - `bootPreview`：记录每次 RAF 触发、previewView 引用、root dimensions
   - 2D/3D view 构造函数：记录 container.innerHTML 清空前后的 childNodes
   - 2D/3D view destroy：记录是否抛异常、canvas 状态
3. 用户复现：打开设置 → 2D → 3D → 2D，观察日志

## Progress

- 2026-07-15: 创建调试会话，启动 Debug Server
