#pragma once

#include "parser.h"
#include <vector>
#include <string>
#include <unordered_set>

namespace memoria {

// 验证结果
struct ValidationResult {
    // 断裂引用: [[id]] 指向的 id 不存在
    std::vector<std::string> broken_citations;

    // 循环依赖: prerequisite 图中的环
    std::vector<std::vector<std::string>> cycles;

    // 孤立节点: 没有任何引用指向它，也没有 prerequisite/extend
    std::vector<std::string> orphan_nodes;

    bool ok() const {
        return broken_citations.empty() && cycles.empty();
    }
};

// 收集所有已定义的节点 id
std::unordered_set<std::string> collect_defined_ids(const std::vector<Document>& docs);

// 验证引用完整性
ValidationResult validate(const std::vector<Document>& docs);

} // namespace memoria
