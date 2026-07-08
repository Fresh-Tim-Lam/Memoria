#include "builder.h"

#include <filesystem>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <set>

namespace memoria {

namespace fs = std::filesystem;

// 简单 JSON 字符串转义
static std::string json_escape(const std::string& s) {
    std::ostringstream oss;
    for (char c : s) {
        switch (c) {
            case '"':  oss << "\\\""; break;
            case '\\': oss << "\\\\"; break;
            case '\n': oss << "\\n";  break;
            case '\r': oss << "\\r";  break;
            case '\t': oss << "\\t";  break;
            default:
                if (static_cast<unsigned char>(c) < 0x20) {
                    oss << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                        << static_cast<int>(c);
                } else {
                    oss << c;
                }
        }
    }
    return oss.str();
}

// 构建 index.json
static std::string build_index_json(const std::vector<Document>& docs) {
    std::ostringstream oss;
    oss << "{\n";

    // nodes 数组
    oss << "  \"nodes\": [\n";
    bool first_node = true;
    for (const auto& doc : docs) {
        for (const auto& node : doc.provides) {
            if (!first_node) oss << ",\n";
            first_node = false;

            oss << "    {\n";
            oss << "      \"id\": \"" << json_escape(node.id) << "\",\n";
            oss << "      \"title\": \"" << json_escape(node.title) << "\",\n";
            oss << "      \"file\": \"" << json_escape(doc.file) << "\",\n";
            if (!node.anchor.empty()) {
                oss << "      \"anchor\": \"" << json_escape(node.anchor) << "\",\n";
            }

            // tags
            oss << "      \"tags\": [";
            for (size_t i = 0; i < doc.tags.size(); ++i) {
                if (i > 0) oss << ", ";
                oss << "\"" << json_escape(doc.tags[i]) << "\"";
            }
            oss << "],\n";

            // prerequisite
            oss << "      \"prerequisite\": [";
            for (size_t i = 0; i < doc.prerequisite.size(); ++i) {
                if (i > 0) oss << ", ";
                oss << "\"" << json_escape(doc.prerequisite[i]) << "\"";
            }
            oss << "],\n";

            // extend
            oss << "      \"extend\": [";
            for (size_t i = 0; i < doc.extend.size(); ++i) {
                if (i > 0) oss << ", ";
                oss << "\"" << json_escape(doc.extend[i]) << "\"";
            }
            oss << "],\n";

            // analogy
            oss << "      \"analogy\": [";
            for (size_t i = 0; i < doc.analogy.size(); ++i) {
                if (i > 0) oss << ", ";
                oss << "\"" << json_escape(doc.analogy[i]) << "\"";
            }
            oss << "]\n";

            oss << "    }";
        }
    }
    oss << "\n  ],\n";

    // citations 数组
    oss << "  \"citations\": [\n";
    bool first_cite = true;
    for (const auto& doc : docs) {
        for (const auto& cite : doc.citations) {
            if (!first_cite) oss << ",\n";
            first_cite = false;

            oss << "    {\n";
            oss << "      \"source\": \"" << json_escape(doc.id) << "\",\n";
            oss << "      \"target\": \"" << json_escape(cite.target_id) << "\",\n";
            oss << "      \"line\": " << cite.line << "\n";
            oss << "    }";
        }
    }
    oss << "\n  ],\n";

    // anchors 数组
    oss << "  \"anchors\": [\n";
    bool first_anchor = true;
    for (const auto& doc : docs) {
        for (const auto& anchor : doc.anchors) {
            if (!first_anchor) oss << ",\n";
            first_anchor = false;

            oss << "    {\n";
            oss << "      \"node\": \"" << json_escape(doc.id) << "\",\n";
            oss << "      \"id\": \"" << json_escape(anchor.id) << "\",\n";
            oss << "      \"line\": " << anchor.line << "\n";
            oss << "    }";
        }
    }
    oss << "\n  ]\n";

    oss << "}\n";
    return oss.str();
}

// 构建 graph.json (D3.js force-directed graph format)
static std::string build_graph_json(const std::vector<Document>& docs) {
    std::ostringstream oss;
    oss << "{\n";

    // nodes
    oss << "  \"nodes\": [\n";
    bool first = true;
    for (const auto& doc : docs) {
        for (const auto& node : doc.provides) {
            if (!first) oss << ",\n";
            first = false;
            oss << "    {\"id\": \"" << json_escape(node.id) << "\", "
                << "\"title\": \"" << json_escape(node.title) << "\"}";
        }
    }
    oss << "\n  ],\n";

    // links
    oss << "  \"links\": [\n";
    first = true;
    for (const auto& doc : docs) {
        for (const auto& node : doc.provides) {
            // prerequisite 边
            for (const auto& prereq : doc.prerequisite) {
                if (!first) oss << ",\n";
                first = false;
                oss << "    {\"source\": \"" << json_escape(prereq) << "\", "
                    << "\"target\": \"" << json_escape(node.id) << "\", "
                    << "\"type\": \"prerequisite\"}";
            }
            // extend 边
            for (const auto& ext : doc.extend) {
                if (!first) oss << ",\n";
                first = false;
                oss << "    {\"source\": \"" << json_escape(node.id) << "\", "
                    << "\"target\": \"" << json_escape(ext) << "\", "
                    << "\"type\": \"extend\"}";
            }
            // analogy 边
            for (const auto& ana : doc.analogy) {
                if (!first) oss << ",\n";
                first = false;
                oss << "    {\"source\": \"" << json_escape(node.id) << "\", "
                    << "\"target\": \"" << json_escape(ana) << "\", "
                    << "\"type\": \"analogy\"}";
            }
        }
    }
    oss << "\n  ]\n";

    oss << "}\n";
    return oss.str();
}

BuildResult build(const std::vector<Document>& docs,
                  const ValidationResult& validation,
                  const std::string& output_dir) {
    BuildResult result;
    result.file_count = static_cast<int>(docs.size());

    // 创建输出目录
    fs::path out(output_dir);
    fs::create_directories(out);

    // 写 index.json（含每个节点的 file 字段指向源文件）
    {
        std::ofstream f(out / "index.json");
        f << build_index_json(docs);
    }

    // 写 graph.json
    {
        std::ofstream f(out / "graph.json");
        f << build_graph_json(docs);
    }

    // 不再写 content/{id}.md 副本
    // reader 直接通过 index.json 的 file 字段读源文件，剥掉 Frontmatter
    for (const auto& doc : docs) {
        result.node_count += static_cast<int>(doc.provides.size());
        // 统计关系
        result.relation_count += static_cast<int>(
            doc.prerequisite.size() + doc.extend.size() + doc.analogy.size());
        result.citation_count += static_cast<int>(doc.citations.size());
        result.anchor_count += static_cast<int>(doc.anchors.size());
    }

    // 验证警告
    for (const auto& broken : validation.broken_citations) {
        result.warnings.push_back("Broken citation: " + broken);
    }
    for (const auto& cycle : validation.cycles) {
        std::string msg = "Cycle: ";
        for (size_t i = 0; i < cycle.size(); ++i) {
            if (i > 0) msg += " -> ";
            msg += cycle[i];
        }
        result.warnings.push_back(msg);
    }

    return result;
}

} // namespace memoria
