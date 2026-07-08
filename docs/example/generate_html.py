# -*- coding: utf-8 -*-
"""
将 人工智能导论知识点汇总 目录下的所有 markdown 文件
合并为单个 HTML 文件，支持目录跳转和数学公式渲染。
"""
import json
from pathlib import Path

base = Path(r"d:\AAA_Jupyter\Memoria\docs\example\人工智能导论知识点汇总")

modules_order = [
    "模块1：人工智能的发展历史",
    "模块2：知识表达与推理",
    "模块3：搜索探寻与问题求解",
    "模块4：机器学习",
    "模块5：深度学习",
    "模块6：强化学习",
    "模块7：人工智能博弈",
    "模块8：人工智能伦理与安全",
    "模块9：人工智能架构与系统",
    "模块10：人工智能应用",
]

all_content = []
for module in modules_order:
    module_path = base / module
    if not module_path.exists():
        print(f"[WARN] 未找到模块目录: {module}")
        continue
    md_files = sorted(module_path.glob("*.md"), key=lambda x: int(x.stem))
    for md_file in md_files:
        text = md_file.read_text(encoding='utf-8')
        all_content.append(text)
        print(f"[OK] 读取 {module}/{md_file.name} ({len(text)} 字符)")

full_markdown = "\n\n".join(all_content)
markdown_json = json.dumps(full_markdown, ensure_ascii=False)
print(f"\n[INFO] 合并后总字符数: {len(full_markdown)}")

# JS 渲染代码（使用 raw string 保留反斜杠）
js_code = r'''// ===== 1. 保护数学公式（防止被 marked.js 破坏）=====
const mathBlocks = {};
let mathIdCounter = 0;
let processed = MARKDOWN_DATA;

// 先保护块级公式 \[...\]（避免行内公式正则误匹配块级公式内部）
processed = processed.replace(/\\\[([\s\S]*?)\\\]/g, (match) => {
    const id = mathIdCounter++;
    mathBlocks[id] = match;
    return `XMATHPH${id}XMATHPHEND`;
});

// 再保护行内公式 \(...\)
processed = processed.replace(/\\\(([\s\S]*?)\\\)/g, (match) => {
    const id = mathIdCounter++;
    mathBlocks[id] = match;
    return `XMATHPH${id}XMATHPHEND`;
});

// ===== 2. 配置并运行 marked.js =====
marked.setOptions({
  gfm: true,
  breaks: false,
  headerIds: false
});

let htmlContent = marked.parse(processed);

// ===== 3. 还原数学公式 =====
for (const id in mathBlocks) {
    htmlContent = htmlContent.split(`XMATHPH${id}XMATHPHEND`).join(mathBlocks[id]);
}

// ===== 4. 插入 DOM =====
document.getElementById('content').innerHTML = htmlContent;

// ===== 5. 为标题生成 ID 并构建目录 =====
const headings = document.querySelectorAll(
  '#content h1, #content h2, #content h3, #content h4, #content h5, #content h6'
);
const toc = document.getElementById('toc-content');

headings.forEach((h, i) => {
    if (!h.id) {
        h.id = 'heading-' + i;
    }
    const link = document.createElement('a');
    link.href = '#' + h.id;
    link.textContent = h.textContent;
    link.className = 'toc-' + h.tagName.toLowerCase();
    toc.appendChild(link);
});

// ===== 6. 显示内容，隐藏 loading =====
document.getElementById('loading').style.display = 'none';
document.getElementById('toc-sidebar').style.display = 'block';
document.getElementById('main-content').style.display = 'block';

// ===== 7. 渲染 MathJax =====
function renderMath() {
    if (window.MathJax && MathJax.typesetPromise) {
        MathJax.typesetPromise([document.getElementById('content')])
            .then(() => { console.log('MathJax 渲染完成'); })
            .catch((err) => { console.error('MathJax 错误:', err); });
    } else {
        setTimeout(renderMath, 100);
    }
}
renderMath();

// ===== 8. 目录点击平滑滚动 =====
document.querySelectorAll('#toc-content a').forEach(link => {
    link.addEventListener('click', (e) => {
        e.preventDefault();
        const targetId = link.getAttribute('href').slice(1);
        const target = document.getElementById(targetId);
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            history.replaceState(null, '', '#' + targetId);
        }
    });
});
'''

html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>人工智能导论知识点汇总</title>
<style>
* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, "Noto Sans", "PingFang SC", "Microsoft YaHei",
    "Hiragino Sans GB", sans-serif;
  line-height: 1.75;
  color: #24292e;
  background: #fff;
  margin: 0;
  padding: 0;
}}

/* ===== 侧边栏目录 ===== */
#toc-sidebar {{
  position: fixed;
  top: 0;
  left: 0;
  width: 320px;
  height: 100vh;
  overflow-y: auto;
  padding: 24px 20px 60px 20px;
  background: #f6f8fa;
  border-right: 1px solid #e1e4e8;
  z-index: 10;
}}
#toc-sidebar h2 {{
  font-size: 18px;
  margin: 0 0 16px 0;
  padding-bottom: 10px;
  border-bottom: 2px solid #0366d6;
  color: #0366d6;
  letter-spacing: 1px;
}}
#toc-content a {{
  display: block;
  padding: 5px 10px;
  color: #586069;
  text-decoration: none;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.45;
  word-break: break-word;
  transition: all 0.15s;
  border-left: 2px solid transparent;
}}
#toc-content a:hover {{
  background: #dbe9f9;
  color: #0366d6;
  border-left-color: #0366d6;
}}
#toc-content a.toc-h3 {{
  font-weight: 600;
  color: #24292e;
  margin-top: 12px;
  font-size: 14px;
}}
#toc-content a.toc-h4 {{
  padding-left: 24px;
  font-size: 12.5px;
}}
#toc-content a.toc-h5 {{
  padding-left: 36px;
  font-size: 12px;
}}

/* ===== 主内容区 ===== */
#main-content {{
  margin-left: 320px;
  padding: 40px 60px 80px 60px;
  max-width: 1000px;
}}

/* ===== 标题 ===== */
#content h1 {{
  font-size: 28px;
  border-bottom: 3px solid #0366d6;
  padding-bottom: 10px;
  color: #0366d6;
  margin-top: 2em;
}}
#content h2 {{
  font-size: 24px;
  border-bottom: 2px solid #d0d7de;
  padding-bottom: 8px;
  margin-top: 2em;
}}
#content h3 {{
  font-size: 20px;
  border-bottom: 2px solid #0366d6;
  padding-bottom: 8px;
  color: #0366d6;
  margin-top: 2em;
}}
#content h4 {{
  font-size: 17px;
  color: #0366d6;
  border-left: 4px solid #0366d6;
  padding-left: 12px;
  margin-top: 1.8em;
}}
#content h5, #content h6 {{
  font-size: 15px;
  color: #1f2328;
  margin-top: 1.5em;
}}

#content p {{ margin: 0.8em 0; }}

/* ===== 表格 ===== */
#content table {{
  border-collapse: collapse;
  margin: 1.2em 0;
  width: 100%;
  font-size: 14px;
  overflow-x: auto;
  display: block;
}}
#content thead {{ background: #f6f8fa; }}
#content th, #content td {{
  border: 1px solid #d0d7de;
  padding: 8px 12px;
  text-align: left;
  vertical-align: top;
}}
#content th {{
  font-weight: 600;
  background: #f6f8fa;
}}
#content tr:nth-child(even) td {{
  background: #fafbfc;
}}

/* ===== 代码 ===== */
#content code {{
  background: rgba(175, 184, 193, 0.2);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 0.9em;
  color: #d6336c;
}}
#content pre {{
  background: #f6f8fa;
  padding: 16px;
  border-radius: 6px;
  overflow-x: auto;
  border: 1px solid #e1e4e8;
}}
#content pre code {{
  background: none;
  padding: 0;
  color: #24292e;
}}

/* ===== 引用、分隔线、列表 ===== */
#content blockquote {{
  border-left: 4px solid #0366d6;
  padding: 8px 16px;
  color: #6a737d;
  margin: 1em 0;
  background: #f6f8fa;
  border-radius: 0 4px 4px 0;
}}
#content hr {{
  border: none;
  border-top: 2px solid #e1e4e8;
  margin: 2.5em 0;
}}
#content ul, #content ol {{
  padding-left: 28px;
}}
#content li {{
  margin: 5px 0;
}}
#content strong {{
  color: #1f2328;
  font-weight: 600;
}}
#content a {{
  color: #0366d6;
  text-decoration: none;
}}
#content a:hover {{ text-decoration: underline; }}

/* ===== MathJax 显示 ===== */
mjx-container {{
  overflow-x: auto;
  overflow-y: hidden;
}}
mjx-container[display="true"] {{
  margin: 1em 0 !important;
}}

/* ===== Loading ===== */
#loading {{
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 20px;
  color: #0366d6;
  text-align: center;
}}
#loading .spinner {{
  width: 40px;
  height: 40px;
  border: 4px solid #e1e4e8;
  border-top-color: #0366d6;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 0 auto 16px;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}

/* ===== 返回顶部按钮 ===== */
#back-to-top {{
  position: fixed;
  bottom: 30px;
  right: 30px;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: #0366d6;
  color: #fff;
  border: none;
  cursor: pointer;
  font-size: 20px;
  display: none;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
  align-items: center;
  justify-content: center;
}}
#back-to-top:hover {{ background: #0256c7; }}
#back-to-top.show {{ display: flex; }}

/* ===== 响应式 ===== */
@media (max-width: 900px) {{
  #toc-sidebar {{
    position: relative;
    width: 100%;
    height: auto;
    max-height: 300px;
    border-right: none;
    border-bottom: 1px solid #e1e4e8;
  }}
  #main-content {{
    margin-left: 0;
    padding: 24px 20px 60px 20px;
    max-width: 100%;
  }}
}}
</style>

<!-- marked.js：Markdown 渲染 -->
<script src="https://cdn.jsdelivr.net/npm/marked@9.1.6/marked.min.js"></script>

<!-- MathJax v3：数学公式渲染（兼容性最高） -->
<script>
MathJax = {{
  tex: {{
    inlineMath: [['\\\\(', '\\\\)']],
    displayMath: [['\\\\[', '\\\\]']],
    processEscapes: true,
    processEnvironments: true,
    loadPackages: {{ '[+]': ['ams', 'amssymb', 'boldsymbol'] }}
  }},
  chtml: {{
    scale: 1.0,
    minScale: 0.5,
    matchFontHeight: false,
    mtextInheritFont: true,
    merrorInheritFont: true
  }},
  svg: {{
    scale: 1.0,
    minScale: 0.5,
    fontCache: 'global'
  }},
  options: {{
    renderActions: {{
      addMenu: [],
      checkLoading: []
    }},
    ignoreHtmlClass: 'no-mathjax'
  }}
}};
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
</head>
<body>

<div id="loading">
  <div class="spinner"></div>
  <div>正在加载知识点...</div>
</div>

<div id="toc-sidebar" style="display:none;">
  <h2>📑 目录</h2>
  <div id="toc-content"></div>
</div>

<div id="main-content" style="display:none;">
  <div id="content"></div>
</div>

<button id="back-to-top" title="返回顶部">↑</button>

<script>
const MARKDOWN_DATA = {markdown_json};
{js_code}
</script>

<script>
// 返回顶部按钮逻辑
window.addEventListener('scroll', () => {{
    const btn = document.getElementById('back-to-top');
    if (window.scrollY > 400) {{
        btn.classList.add('show');
    }} else {{
        btn.classList.remove('show');
    }}
}});
document.getElementById('back-to-top').addEventListener('click', () => {{
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
}});
</script>

</body>
</html>
'''

output_path = base / "人工智能导论知识点汇总.html"
output_path.write_text(html, encoding='utf-8')
print(f"\n[DONE] 已生成 HTML 文件: {output_path}")
print(f"[INFO] 文件大小: {output_path.stat().st_size / 1024:.1f} KB")
