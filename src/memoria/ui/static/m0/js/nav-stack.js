/**
 * 导航历史栈（designV0 §12 简化版：timeline + cursor + filePointer）
 */
window.MemoriaNavStack = (function () {
  "use strict";

  let stack = [];
  let cursor = -1;
  const filePointer = Object.create(null);

  function clear() {
    stack = [];
    cursor = -1;
    for (const k of Object.keys(filePointer)) {
      delete filePointer[k];
    }
  }

  function current() {
    return cursor >= 0 ? stack[cursor] : null;
  }

  function push(frame) {
    if (cursor < stack.length - 1) {
      stack = stack.slice(0, cursor + 1);
    }
    const entry = {
      file: frame.file,
      kpId: frame.kpId || null,
      source: frame.source || null,
    };
    stack.push(entry);
    cursor = stack.length - 1;
    filePointer[frame.file] = cursor;
    return entry;
  }

  function openFileFromTree(file) {
    const ptr = filePointer[file];
    if (ptr != null && stack[ptr] && stack[ptr].file === file) {
      cursor = ptr;
      stack = stack.slice(0, cursor + 1);
      return stack[cursor];
    }
    return push({ file, kpId: null, source: "tree" });
  }

  function navBack() {
    if (cursor <= 0) return null;
    cursor -= 1;
    return stack[cursor];
  }

  function navForward() {
    if (cursor >= stack.length - 1) return null;
    cursor += 1;
    return stack[cursor];
  }

  function canBack() {
    return cursor > 0;
  }

  function canForward() {
    return cursor >= 0 && cursor < stack.length - 1;
  }

  return {
    clear,
    current,
    push,
    openFileFromTree,
    navBack,
    navForward,
    canBack,
    canForward,
  };
})();
