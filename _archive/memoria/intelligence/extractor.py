"""知识点提取器

从 Markdown 文件中提取知识点信号，用于 Embedding 输入构造。

权重设计：
- provides (信号A): 高权重 - 文档显式声明"我提供这个知识"
- tags (信号C): 高权重 - 用户定义的主题标签
- jieba术语 (信号D): 中权重 - 正文术语
- [[id]]引用 (信号B): 极低权重 - 文档只是提及，不是主体
"""
import os
import re
import tempfile
from typing import List, Dict, Set, Tuple

# 将 jieba 缓存重定向到项目目录而非 C 盘临时目录
# jieba 使用 tempfile.gettempdir() 决定缓存位置
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PROJECT_CACHE = os.path.join(_PROJECT_ROOT, ".cache")
os.makedirs(_PROJECT_CACHE, exist_ok=True)
# 仅当系统 temp 不在我们项目内时才覆盖（避免影响其他工具）
if not tempfile.gettempdir().startswith(_PROJECT_CACHE):
    tempfile.tempdir = _PROJECT_CACHE


def extract_from_node(node: dict, content: str) -> dict:
    """
    从单个节点提取知识点信号

    Args:
        node: index.json 中的节点对象（含 id, title, tags, provides, prerequisite 等）
        content: 节点的 Markdown 正文（已去除 Frontmatter）

    Returns:
        {
            "provides": [...],      # 信号A: 高权重
            "tags": [...],          # 信号C: 高权重
            "jieba_terms": [...],   # 信号D: 中权重
            "cited_ids": [...],     # 信号B: 极低权重（[[id]] 引用）
            "all_keywords": [...]   # 去重后的所有关键词
        }
    """
    # 信号 A: provides 字段
    provides = []
    if "provides" in node and isinstance(node["provides"], list):
        for p in node["provides"]:
            if isinstance(p, dict):
                if p.get("title"):
                    provides.append(p["title"])
                if p.get("id") and p["id"] != node.get("id"):
                    provides.append(p["id"])
    # 如果没有 provides，用 title 作为 provides
    if not provides and node.get("title"):
        provides.append(node["title"])

    # 信号 C: tags
    tags = node.get("tags", []) if isinstance(node.get("tags"), list) else []

    # 信号 B: [[id]] 引用（极低权重）
    cited_ids = re.findall(r'\[\[([^\]]+)\]\]', content)
    # 处理 [[id#anchor]] 和 [[id|text]] 和 [[id#anchor|text]] 格式
    # 先取 | 之前的部分（去掉显示文本），再取 # 之前的部分（去掉锚点）
    cited_ids = [c.split("|")[0].split("#")[0] for c in cited_ids]
    # 去除自身引用
    cited_ids = [c for c in cited_ids if c != node.get("id")]

    # 信号 D: jieba 正文术语
    jieba_terms = _extract_jieba_terms(content, provides + tags + cited_ids)

    # 去重汇总
    all_keywords = list(set(provides + tags + jieba_terms))

    return {
        "provides": provides,
        "tags": tags,
        "jieba_terms": jieba_terms,
        "cited_ids": cited_ids,
        "all_keywords": all_keywords,
    }


def _extract_jieba_terms(content: str, known_terms: List[str]) -> List[str]:
    """
    用 jieba 从正文提取专业术语

    过滤规则：
    - 长度 >= 2
    - 排除常见停用词
    - 排除已知术语（避免重复）
    - 词性为名词(n)、英文(eng)、其他名词相关(nr/ns/nt/nz)

    优化：将已知术语加入 jieba 词典，避免被拆碎
    """
    import jieba.posseg as pseg
    import jieba

    # 将已知术语加入 jieba 词典，防止拆分
    # 例如 "actor-critic" 不被拆成 "actor" + "critic"
    for term in known_terms:
        if len(term) >= 3:
            jieba.add_word(term, freq=1000, tag='nz')

    # 停用词表（常见无意义词）
    stop_words = {
        "我们", "可以", "一种", "用于", "通过", "进行", "以及", "包括",
        "例如", "如下", "如下所示", "其中", "这个", "这些", "那种", "那种",
        "什么", "怎么", "如何", "为什么", "因为", "所以", "但是", "然而",
        "虽然", "尽管", "如果", "那么", "就是", "还是", "或者", "并且",
        "以及", "还有", "主要", "重要", "基本", "基础", "概念", "方法",
        "方式", "过程", "结果", "问题", "目标", "目的", "作用", "功能",
        "结构", "组件", "部分", "内容", "形式", "类型", "种类", "类别",
        "他们", "它们", "它们", "自己", "本身", "一样", "同样", "不同",
        "这样", "那样", "这里", "那里", "哪里", "什么", "怎么", "为什么",
        "一个", "两个", "三个", "第一", "第二", "第三", "最后", "首先",
        "已经", "正在", "将要", "将会", "可以", "应该", "必须", "需要",
        "得到", "获得", "实现", "完成", "开始", "结束", "继续", "停止",
        "使用", "利用", "采用", "选择", "选取", "选取", "选出", "找出",
        "然后", "接着", "随后", "之后", "之前", "期间", "此时", "彼时",
        "生成", "产生", "创建", "建立", "构建", "形成", "组成", "构成",
        "表示", "说明", "解释", "描述", "阐述", "介绍", "展示", "呈现",
        "基于", "根据", "按照", "依据", "参照", "参考", "结合", "整合",
        "本文", "本节", "本章", "本书", "此处", "此节", "此章", "此书",
        "如下", "上述", "前面", "后面", "上面", "下面", "里面", "外面",
        "即", "则", "为", "是", "有", "在", "和", "与", "或", "及", "等",
        "动作", "空间", "架构", "网络", "机制", "核心", "循环", "序列", "编码",
    }

    # 去除 Markdown 标记
    clean_content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)  # 代码块
    clean_content = re.sub(r'\[\[([^\]]+)\]\]', '', clean_content)  # [[id]] 引用
    clean_content = re.sub(r'\[:anchor:[^\]]+\]', '', clean_content)  # 锚点
    clean_content = re.sub(r'[#*`\-|>]', '', clean_content)  # Markdown 符号
    clean_content = re.sub(r'\$[^$]+\$', '', clean_content)  # 行内公式

    # 分词 + 词性标注
    terms = []
    known_set = set(known_terms)
    seen = set()

    for word, flag in pseg.cut(clean_content):
        # 过滤条件
        if len(word) < 2:
            continue
        if word in stop_words:
            continue
        if word in known_set:
            continue
        if word in seen:
            continue
        # 只保留名词类词性
        if flag not in ('n', 'nr', 'ns', 'nt', 'nz', 'eng', 'vn'):
            continue
        # 过滤纯数字
        if word.isdigit():
            continue

        terms.append(word)
        seen.add(word)

        # 每个文档最多提取 15 个术语，避免过多
        if len(terms) >= 15:
            break

    return terms


def build_embedding_text(extracted: dict) -> str:
    """
    根据提取结果构造 Embedding 输入文本

    权重通过重复实现：
    - provides: 重复 2 次（高权重）
    - tags: 重复 2 次（高权重）
    - user_added: 重复 2 次（高权重，用户明确添加的）
    - jieba_terms: 1 次（中权重）
    - cited_ids: 1 次（极低权重，不重复）
    """
    parts = []

    # 高权重：provides 重复 2 次
    if extracted["provides"]:
        provides_str = " ".join(extracted["provides"])
        parts.append(provides_str)
        parts.append(provides_str)

    # 高权重：tags 重复 2 次
    if extracted["tags"]:
        tags_str = " ".join(extracted["tags"])
        parts.append(tags_str)
        parts.append(tags_str)

    # 高权重：用户手动添加的关键词重复 2 次
    if extracted.get("user_added"):
        user_str = " ".join(extracted["user_added"])
        parts.append(user_str)
        parts.append(user_str)

    # 中权重：jieba 术语 1 次
    if extracted["jieba_terms"]:
        parts.append(" ".join(extracted["jieba_terms"]))

    # 极低权重：[[id]] 引用 1 次（不重复）
    if extracted["cited_ids"]:
        parts.append(" ".join(extracted["cited_ids"]))

    return " ".join(parts)


def apply_user_review(extracted: dict, user_config: dict) -> dict:
    """
    应用用户审核结果

    Args:
        extracted: 自动提取的结果
        user_config: 用户审核配置
            {
                "user_added": [...],      # 用户增加的关键词
                "user_removed": [...],    # 用户删除的关键词
                "user_edited": {old: new} # 用户修改的关键词
            }

    Returns:
        应用审核后的 extracted 副本
    """
    import copy
    result = copy.deepcopy(extracted)

    # 应用删除
    removed_set = set(user_config.get("user_removed", []))
    result["provides"] = [x for x in result["provides"] if x not in removed_set]
    result["tags"] = [x for x in result["tags"] if x not in removed_set]
    result["jieba_terms"] = [x for x in result["jieba_terms"] if x not in removed_set]
    result["cited_ids"] = [x for x in result["cited_ids"] if x not in removed_set]

    # 应用修改
    edits = user_config.get("user_edited", {})
    for old, new in edits.items():
        for key in ["provides", "tags", "jieba_terms", "cited_ids"]:
            if old in result[key]:
                idx = result[key].index(old)
                result[key][idx] = new

    # 应用增加（用户手动添加的词用高权重，独立存放）
    result["user_added"] = list(user_config.get("user_added", []))

    # 重新计算 all_keywords
    result["all_keywords"] = list(set(
        result["provides"] + result["tags"] + result["jieba_terms"] + result["user_added"]
    ))

    return result
