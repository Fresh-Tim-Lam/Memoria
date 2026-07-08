#pragma once

#include <string>
#include <vector>
#include <unordered_map>

namespace memoria {

// 单个知识节点（provides 展开后的独立节点）
struct Node {
    std::string id;           // 节点 id（provides 中的 id）
    std::string title;        // 节点标题
    std::string anchor;       // 文内锚点
    std::string file;         // 所属 .md 文件路径
    std::vector<std::string> tags;
};

// 文档级信息（一个 .md 文件对应一个 Document）
struct Document {
    std::string file;         // 文件路径
    std::string id;           // Frontmatter 中的 id
    std::string title;        // Frontmatter 中的 title
    std::vector<Node> provides;  // provides 列表（展开后的节点）
    std::vector<std::string> prerequisite;  // 前置依赖 id 列表
    std::vector<std::string> extend;        // 扩展 id 列表
    std::vector<std::string> analogy;       // 类比 id 列表
    std::vector<std::string> tags;          // 标签
    std::string body;         // Frontmatter 之后的正文

    // 从正文中提取的 [[id]] 引用（带出现位置）
    struct Citation {
        std::string target_id;
        std::string context;  // 引用周围的上下文
        int line;             // 行号
    };
    std::vector<Citation> citations;

    // 从正文中提取的 [:anchor:xxx] 锚点
    struct Anchor {
        std::string id;
        std::string heading;  // 所属标题
        int line;
    };
    std::vector<Anchor> anchors;
};

// 解析单个 .md 文件
// 返回解析后的 Document，失败时返回空的 Document（file 为空）
Document parse_file(const std::string& file_path);

// 从文本中提取所有 [[id]] 引用
std::vector<std::pair<std::string, int>> extract_citations(const std::string& text);

// 从文本中提取所有 [:anchor:xxx] 锚点
std::vector<std::pair<std::string, int>> extract_anchors(const std::string& text);

} // namespace memoria
