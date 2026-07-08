# -*- coding: utf-8 -*-
"""
将 人工智能导论知识点汇总 目录下的所有 markdown 文件
合并为单个 HTML 文件（Python 预渲染，不依赖 marked.js）。
数学公式使用 MathJax v3 渲染（兼容性最高）。
"""
import markdown
import re
from pathlib import Path
from html import escape

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

# ===== 1. 读取所有 markdown 文件 =====
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
print(f"\n[INFO] 合并后总字符数: {len(full_markdown)}")

# ===== 2. 保护数学公式（防止被 markdown 库破坏）=====
math_blocks = {}
math_counter = [0]

def protect_display_math(match):
    mid = math_counter[0]
    math_counter[0] += 1
    math_blocks[mid] = match.group(0)
    return f"XMATHPH{mid}XMATHPHEND"

def protect_inline_math(match):
    mid = math_counter[0]
    math_counter[0] += 1
    math_blocks[mid] = match.group(0)
    return f"XMATHPH{mid}XMATHPHEND"

processed = full_markdown
# 先保护块级公式 \[...\]
processed = re.sub(r'\\\[([\s\S]*?)\\\]', protect_display_math, processed)
# 再保护行内公式 \(...\)
processed = re.sub(r'\\\(([\s\S]*?)\\\)', protect_inline_math, processed)
print(f"[INFO] 保护了 {len(math_blocks)} 个数学公式")

# ===== 2.4 转义 < 和 > =====
# 防止浏览器将 <left_node, ...> 这类文本误解析为 HTML 标签
# 注意：此时数学公式已被替换为占位符（不含 < >），所以不会影响公式
# 1) 先把 \< 和 \> 转成实体（markdown 库不支持 \< \> 转义，会残留反斜杠）
processed = processed.replace('\\<', '&lt;')
processed = processed.replace('\\>', '&gt;')
# 2) 再转义剩余未被反斜杠转义的 < 和 >
processed = re.sub(r'(?<!\\)<', '&lt;', processed)
processed = re.sub(r'(?<!\\)>', '&gt;', processed)
print(f"[INFO] 转义 < 和 > 完成")

# ===== 2.5 预处理：在列表前插入空行（让 markdown 库正确识别列表）=====
def add_blank_lines_before_lists(text):
    """在紧跟非空行的列表项前插入空行，确保 markdown 库正确识别列表"""
    lines = text.split('\n')
    result = []
    list_pattern = re.compile(r'^(\s*)([-*+]|\d+\.)\s+')
    for i, line in enumerate(lines):
        is_list_item = bool(list_pattern.match(line))
        if is_list_item and result:
            prev_line = result[-1]
            prev_is_list = bool(list_pattern.match(prev_line))
            prev_is_blank = prev_line.strip() == ''
            prev_is_indent_cont = prev_line.startswith('  ') and prev_line.strip() != ''
            # 如果上一行非空、非列表项、非缩进续行，则插入空行
            if not prev_is_blank and not prev_is_list and not prev_is_indent_cont:
                result.append('')
        result.append(line)
    return '\n'.join(result)

processed = add_blank_lines_before_lists(processed)
print(f"[INFO] 预处理列表完成")

# ===== 3. 自定义 slugify 函数（支持中文）=====
def chinese_slug(value, separator='-'):
    # 保留中文、字母、数字、连字符
    value = re.sub(r'[^\w\u4e00-\u9fff]+', separator, value, flags=re.UNICODE)
    value = value.strip(separator).lower()
    return value if value else 'section'

# ===== 4. 转换 markdown 为 HTML =====
md_converter = markdown.Markdown(
    extensions=['tables', 'fenced_code', 'toc'],
    extension_configs={
        'toc': {
            'permalink': False,
            'slugify': chinese_slug,
        }
    }
)
html_content = md_converter.convert(processed)
print(f"[INFO] markdown 转换完成，HTML 长度: {len(html_content)}")

# ===== 5. 还原数学公式 =====
for mid, math in math_blocks.items():
    html_content = html_content.replace(f"XMATHPH{mid}XMATHPHEND", math)

# ===== 6. 提取标题构建目录 =====
# 匹配 <hN ... id="..." ...>内容</hN>
heading_pattern = re.compile(
    r'<(h[1-6])\s+([^>]*?)>(.*?)</\1>',
    re.DOTALL
)
id_pattern = re.compile(r'id="([^"]+)"')

toc_items = []
def collect_headings(match):
    tag = match.group(1)
    attrs = match.group(2)
    content = match.group(3)
    # 去除 HTML 标签获取纯文本
    clean_text = re.sub(r'<[^>]+>', '', content)
    clean_text = clean_text.strip()
    if not clean_text:
        return match.group(0)
    # 查找已有的 id
    id_match = id_pattern.search(attrs)
    if id_match:
        hid = id_match.group(1)
    else:
        hid = f'heading-{len(toc_items)}'
        # 给标题添加 id
        new_attrs = f' id="{hid}"'
        if attrs:
            new_attrs += ' ' + attrs
        return f'<{tag}{new_attrs}>{content}</{tag}>'
    toc_items.append((tag, hid, clean_text))
    return match.group(0)

html_content = heading_pattern.sub(collect_headings, html_content)

# 重新扫描一次，收集所有标题（包括刚添加 id 的）
toc_items = []
def collect_all_headings(match):
    tag = match.group(1)
    attrs = match.group(2)
    content = match.group(3)
    clean_text = re.sub(r'<[^>]+>', '', content).strip()
    if not clean_text:
        return
    id_match = id_pattern.search(attrs)
    if id_match:
        toc_items.append((tag, id_match.group(1), clean_text))

heading_pattern.sub(collect_all_headings, html_content)

# 构建目录 HTML
toc_html = ''
for tag, hid, text in toc_items:
    toc_html += f'<a href="#{escape(hid)}" class="toc-{tag}">{escape(text)}</a>\n'

print(f"[INFO] 提取了 {len(toc_items)} 个目录项")

# ===== 7. 生成最终 HTML =====
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
#toc-content a.toc-h2 {{
  font-weight: 700;
  color: #0366d6;
  font-size: 15px;
  margin-top: 16px;
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
#content h3, #content h4 {{
  scroll-margin-top: 20px;
}}

#content p {{ margin: 0.8em 0; }}

/* ===== 表格 ===== */
#content table {{
  border-collapse: collapse;
  margin: 1.2em 0;
  width: 100%;
  font-size: 14px;
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

<!-- MathJax v3：数学公式渲染（本地优先 + CDN 回退，兼容性最高） -->
<script>
MathJax = {{
  tex: {{
    inlineMath: [['\\\\(', '\\\\)']],
    displayMath: [['\\\\[', '\\\\]']],
    processEscapes: true,
    processEnvironments: true,
    packages: {{ '[+]': ['ams', 'amssymb', 'boldsymbol'] }}
  }},
  svg: {{
    scale: 1.0,
    minScale: 0.5,
    fontCache: 'global',
    mtextInheritFont: true,
    merrorInheritFont: true
  }},
  startup: {{
    typeset: true,
    pageReady: () => {{
      return MathJax.startup.defaultPageReady().then(() => {{
        document.body.classList.add('mathjax-ready');
        console.log('MathJax 渲染完成');
      }});
    }}
  }}
}};
</script>
<script>
// 加载策略：本地 tex-svg.js 优先；失败则回退到国内可访问的 CDN
(function() {{
  var sources = [
    './mathjax/tex-svg.js',
    'https://cdn.bootcdn.net/ajax/libs/mathjax/3.2.2/es5/tex-svg.js',
    'https://cdn.staticfile.org/mathjax/3.2.2/es5/tex-svg.js',
    'https://cdn.jsdelivr.net/npm/mathjax@3.2.2/es5/tex-svg.js'
  ];
  var idx = 0;
  function tryLoad() {{
    if (idx >= sources.length) {{
      console.error('所有 MathJax 源均加载失败，数学公式将以原始 LaTeX 显示');
      return;
    }}
    var s = document.createElement('script');
    s.src = sources[idx];
    s.async = false;
    s.onload = function() {{ console.log('MathJax 加载成功: ' + sources[idx]); }};
    s.onerror = function() {{
      console.warn('MathJax 加载失败: ' + sources[idx] + '，尝试下一个源...');
      idx++;
      tryLoad();
    }};
    document.head.appendChild(s);
  }}
  tryLoad();
}})();
</script>
</head>
<body>

<div id="toc-sidebar">
  <h2>📑 目录</h2>
  <div id="toc-content">
{toc_html}  </div>
</div>

<div id="main-content">
  <div id="content">
{html_content}  </div>
</div>

<button id="back-to-top" title="返回顶部">↑</button>

<script>
// 返回顶部按钮逻辑
window.addEventListener('scroll', function() {{
    var btn = document.getElementById('back-to-top');
    if (window.scrollY > 400) {{
        btn.classList.add('show');
    }} else {{
        btn.classList.remove('show');
    }}
}});
document.getElementById('back-to-top').addEventListener('click', function() {{
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
}});

// 目录点击平滑滚动
document.querySelectorAll('#toc-content a').forEach(function(link) {{
    link.addEventListener('click', function(e) {{
        e.preventDefault();
        var targetId = this.getAttribute('href').slice(1);
        var target = document.getElementById(targetId);
        if (target) {{
            target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            history.replaceState(null, '', '#' + targetId);
        }}
    }});
}});
</script>

</body>
</html>
'''

output_path = base / "人工智能导论知识点汇总.html"
output_path.write_text(html, encoding='utf-8')
print(f"\n[DONE] 已生成 HTML 文件: {output_path}")
print(f"[INFO] 文件大小: {output_path.stat().st_size / 1024:.1f} KB")
