#pragma once

#include <string>
#include <vector>

namespace memoria {

// 扫描目录下所有 .md 文件（递归）
// exclude_dirs: 要跳过的目录名（如 ".build", ".nodes"）
// 返回文件路径列表（绝对路径）
std::vector<std::string> scan_directory(
    const std::string& dir_path,
    const std::vector<std::string>& exclude_dirs = {}
);

} // namespace memoria
