#include "validator.h"

#include <unordered_map>
#include <algorithm>
#include <sstream>

namespace memoria {

std::unordered_set<std::string> collect_defined_ids(const std::vector<Document>& docs) {
    std::unordered_set<std::string> ids;
    for (const auto& doc : docs) {
        for (const auto& node : doc.provides) {
            ids.insert(node.id);
        }
        // 也把 doc.id 加入（兼容直接引用文件 id 的情况）
        if (!doc.id.empty()) {
            ids.insert(doc.id);
        }
    }
    return ids;
}

// DFS 检测环
static bool dfs_cycle(
    const std::string& node,
    const std::unordered_map<std::string, std::vector<std::string>>& graph,
    std::unordered_set<std::string>& visiting,
    std::unordered_set<std::string>& visited,
    std::vector<std::string>& path,
    std::vector<std::vector<std::string>>& cycles) {

    visiting.insert(node);
    path.push_back(node);

    bool found_cycle = false;

    auto it = graph.find(node);
    if (it != graph.end()) {
        for (const auto& next : it->second) {
            if (graph.find(next) == graph.end()) continue;  // 目标不在图中

            if (visiting.count(next)) {
                // 找到环
                std::vector<std::string> cycle;
                auto start = std::find(path.begin(), path.end(), next);
                for (auto i = start; i != path.end(); ++i) {
                    cycle.push_back(*i);
                }
                cycle.push_back(next);
                cycles.push_back(cycle);
                found_cycle = true;
            } else if (!visited.count(next)) {
                if (dfs_cycle(next, graph, visiting, visited, path, cycles)) {
                    found_cycle = true;
                }
            }
        }
    }

    path.pop_back();
    visiting.erase(node);
    visited.insert(node);
    return found_cycle;
}

ValidationResult validate(const std::vector<Document>& docs) {
    ValidationResult result;

    auto defined_ids = collect_defined_ids(docs);

    // 1. 检查引用完整性
    for (const auto& doc : docs) {
        for (const auto& cite : doc.citations) {
            if (!defined_ids.count(cite.target_id)) {
                std::string msg = doc.id + " -> [[" + cite.target_id + "]] (line "
                                  + std::to_string(cite.line) + ")";
                result.broken_citations.push_back(msg);
            }
        }
    }

    // 2. 检查 prerequisite 循环依赖
    std::unordered_map<std::string, std::vector<std::string>> graph;
    for (const auto& doc : docs) {
        for (const auto& node : doc.provides) {
            graph[node.id] = {};
        }
    }
    for (const auto& doc : docs) {
        for (const auto& node : doc.provides) {
            for (const auto& prereq : doc.prerequisite) {
                if (graph.count(prereq)) {
                    graph[prereq].push_back(node.id);
                }
            }
        }
    }

    std::unordered_set<std::string> visiting;
    std::unordered_set<std::string> visited;
    std::vector<std::string> path;

    for (const auto& [node, _] : graph) {
        if (!visited.count(node)) {
            dfs_cycle(node, graph, visiting, visited, path, result.cycles);
        }
    }

    // 3. 检查孤立节点
    std::unordered_set<std::string> referenced;
    for (const auto& doc : docs) {
        for (const auto& cite : doc.citations) {
            referenced.insert(cite.target_id);
        }
        for (const auto& id : doc.prerequisite) {
            referenced.insert(id);
        }
        for (const auto& id : doc.extend) {
            referenced.insert(id);
        }
        for (const auto& id : doc.analogy) {
            referenced.insert(id);
        }
    }

    for (const auto& doc : docs) {
        for (const auto& node : doc.provides) {
            // 如果该节点没有引用别人，也没被别人引用
            bool has_prereq = !doc.prerequisite.empty();
            bool has_extend = !doc.extend.empty();
            bool has_analogy = !doc.analogy.empty();
            bool has_citations = !doc.citations.empty();
            bool is_referenced = referenced.count(node.id);

            if (!has_prereq && !has_extend && !has_analogy
                && !has_citations && !is_referenced) {
                result.orphan_nodes.push_back(node.id);
            }
        }
    }

    return result;
}

} // namespace memoria
