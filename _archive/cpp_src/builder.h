#pragma once

#include "parser.h"
#include "validator.h"
#include <string>

namespace memoria {

// 构建产物：输出 build/ 目录
struct BuildResult {
    int node_count = 0;
    int relation_count = 0;
    int citation_count = 0;
    int anchor_count = 0;
    int file_count = 0;
    std::vector<std::string> warnings;
    std::vector<std::string> errors;
};

// 构建索引并输出到 .build/ 目录
// 输出文件:
//   .build/index.json  - 所有节点 + 关系 + 引用（含 file 字段指向源文件）
//   .build/graph.json  - D3.js 力导向图格式
// 注：不再生成 content/ 副本，reader 直接读源文件
BuildResult build(const std::vector<Document>& docs,
                  const ValidationResult& validation,
                  const std::string& output_dir);

} // namespace memoria
