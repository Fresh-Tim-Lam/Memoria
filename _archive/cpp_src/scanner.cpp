#include "scanner.h"

#include <filesystem>
#include <algorithm>
#include <string>

namespace memoria {

namespace fs = std::filesystem;

std::vector<std::string> scan_directory(
    const std::string& dir_path,
    const std::vector<std::string>& exclude_dirs
) {
    std::vector<std::string> files;

    if (!fs::exists(dir_path) || !fs::is_directory(dir_path)) {
        return files;
    }

    // 构建排除集合（小写比较，兼容性更好）
    std::vector<std::string> excludes = exclude_dirs;

    for (const auto& entry : fs::recursive_directory_iterator(dir_path)) {
        // 跳过排除目录下的所有内容
        bool skip = false;
        for (const auto& ex : excludes) {
            // 检查路径中是否有任意一段等于排除目录名
            const auto& p = entry.path();
            for (const auto& part : p) {
                std::string seg = part.string();
                if (seg == ex) {
                    skip = true;
                    break;
                }
            }
            if (skip) break;
        }
        if (skip) continue;

        if (entry.is_regular_file() && entry.path().extension() == ".md") {
            files.push_back(entry.path().string());
        }
    }

    // 排序，保证构建结果稳定
    std::sort(files.begin(), files.end());
    return files;
}

} // namespace memoria
