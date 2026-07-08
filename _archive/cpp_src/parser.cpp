#include "parser.h"

#include <fstream>
#include <sstream>
#include <regex>
#include <algorithm>

#ifdef _WIN32
#include <windows.h>
// UTF-8 字符串转 UTF-16 宽字符串（Windows 专用）
// 解决 std::ifstream 无法打开中文路径的问题
static std::wstring utf8_to_wstring(const std::string& s) {
    if (s.empty()) return std::wstring();
    int len = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.length(), NULL, 0);
    std::wstring buf(len, 0);
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.length(), &buf[0], len);
    return buf;
}
#endif

namespace memoria {

// 跨平台文件读取：Windows 下用宽字符路径支持中文
static std::string read_file_content(const std::string& file_path) {
#ifdef _WIN32
    std::wstring wpath = utf8_to_wstring(file_path);
    std::ifstream ifs(wpath.c_str());
#else
    std::ifstream ifs(file_path);
#endif
    if (!ifs.is_open()) return "";
    std::ostringstream oss;
    oss << ifs.rdbuf();
    return oss.str();
}

// 去除字符串首尾空白
static std::string trim(const std::string& s) {
    size_t start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    size_t end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

// 简单 YAML 解析（仅支持 Memoria 用到的子集）
// 支持: key: value, key: [a, b, c], 多行 provides 列表
static std::unordered_map<std::string, std::string> parse_yaml_simple(
    const std::vector<std::string>& lines, size_t& pos, size_t end) {

    std::unordered_map<std::string, std::string> result;
    std::string current_key;

    while (pos < end) {
        const std::string& line = lines[pos];
        std::string trimmed = trim(line);

        // 空行跳过
        if (trimmed.empty()) { pos++; continue; }

        // 列表项（以 - 开头）归入 current_key
        if (trimmed[0] == '-') {
            if (!current_key.empty()) {
                std::string val = trim(trimmed.substr(1));
                if (result.count(current_key)) {
                    result[current_key] += "\n" + val;
                } else {
                    result[current_key] = val;
                }
            }
            pos++;
            continue;
        }

        // key: value
        size_t colon = trimmed.find(':');
        if (colon == std::string::npos) { pos++; continue; }

        std::string key = trim(trimmed.substr(0, colon));
        std::string value = trim(trimmed.substr(colon + 1));
        current_key = key;

        // 去掉引号
        if (value.size() >= 2 &&
            ((value.front() == '"' && value.back() == '"') ||
             (value.front() == '\'' && value.back() == '\''))) {
            value = value.substr(1, value.size() - 2);
        }

        // [] 形式的数组
        if (value.size() >= 2 && value.front() == '[' && value.back() == ']') {
            std::string inner = value.substr(1, value.size() - 2);
            result[key] = inner;  // 保留原始，后续 split
        } else if (!value.empty()) {
            result[key] = value;
        }
        // value 为空说明是多行列表，等后续 - 行
        pos++;
    }
    return result;
}

// 将 "a, b, c" 或 "a\nb\nc" 或 "[a, b, c]" 拆分为列表
static std::vector<std::string> split_list(std::string s) {
    // 去掉首尾的方括号
    if (s.size() >= 2 && s.front() == '[' && s.back() == ']') {
        s = s.substr(1, s.size() - 2);
    }
    std::vector<std::string> result;
    std::string current;
    for (char c : s) {
        if (c == ',' || c == '\n') {
            std::string t = trim(current);
            if (!t.empty()) result.push_back(t);
            current.clear();
        } else {
            current += c;
        }
    }
    std::string t = trim(current);
    if (!t.empty()) result.push_back(t);
    return result;
}

// 解析 provides 列表（可能含 id, title, anchor 子字段）
// 格式:
//   provides:
//     - id: xxx
//       title: xxx
//       anchor: xxx
//     - id: yyy
//       title: yyy
static std::vector<Node> parse_provides(
    const std::vector<std::string>& lines, size_t& pos, size_t end) {

    std::vector<Node> nodes;
    Node current;
    bool in_node = false;

    while (pos < end) {
        std::string trimmed = trim(lines[pos]);

        if (trimmed.empty()) { pos++; continue; }

        // 新列表项
        if (trimmed[0] == '-' && trimmed.find(':') != std::string::npos) {
            if (in_node) {
                nodes.push_back(current);
                current = Node();
            }
            in_node = true;
            // - id: xxx
            std::string rest = trim(trimmed.substr(1));
            size_t colon = rest.find(':');
            if (colon != std::string::npos) {
                std::string key = trim(rest.substr(0, colon));
                std::string val = trim(rest.substr(colon + 1));
                if (key == "id") current.id = val;
                else if (key == "title") current.title = val;
                else if (key == "anchor") current.anchor = val;
            }
            pos++;
            continue;
        }

        // 续行（缩进的 key: value，必须以空格开头）
        if (in_node && !lines[pos].empty() && lines[pos][0] == ' '
            && trimmed.find(':') != std::string::npos) {
            size_t colon = trimmed.find(':');
            std::string key = trim(trimmed.substr(0, colon));
            std::string val = trim(trimmed.substr(colon + 1));
            if (key == "id") current.id = val;
            else if (key == "title") current.title = val;
            else if (key == "anchor") current.anchor = val;
            pos++;
            continue;
        }

        // 不是列表项也不是续行 → provides 段结束
        break;
    }

    if (in_node && !current.id.empty()) {
        nodes.push_back(current);
    }
    return nodes;
}

// 从 provides 的原始文本解析（简单格式: provides: [a, b, c]）
static std::vector<Node> parse_provides_simple(const std::string& s) {
    std::vector<Node> nodes;
    auto items = split_list(s);
    for (const auto& item : items) {
        Node n;
        n.id = item;
        n.title = item;
        nodes.push_back(n);
    }
    return nodes;
}

std::vector<std::pair<std::string, int>> extract_citations(const std::string& text) {
    std::vector<std::pair<std::string, int>> results;
    // 匹配 [[id]]、[[id#anchor]]、[[id|text]]、[[id#anchor|text]]
    std::regex re(R"(\[\[([^\]]+)\]\])");

    std::stringstream ss(text);
    std::string line;
    int line_num = 0;
    while (std::getline(ss, line)) {
        line_num++;
        auto begin = std::sregex_iterator(line.begin(), line.end(), re);
        auto end_it = std::sregex_iterator();
        for (auto it = begin; it != end_it; ++it) {
            std::string id = (*it)[1].str();
            // 先去掉 |text 部分（显示文本），保留 id#anchor
            size_t pipe = id.find('|');
            if (pipe != std::string::npos) {
                id = id.substr(0, pipe);
            }
            // 再去掉 #anchor 部分
            size_t hash = id.find('#');
            if (hash != std::string::npos) {
                id = id.substr(0, hash);
            }
            results.push_back({id, line_num});
        }
    }
    return results;
}

std::vector<std::pair<std::string, int>> extract_anchors(const std::string& text) {
    std::vector<std::pair<std::string, int>> results;
    // 匹配 [:anchor:xxx]
    std::regex re(R"(\[:anchor:([^\]]+)\])");

    std::stringstream ss(text);
    std::string line;
    int line_num = 0;
    while (std::getline(ss, line)) {
        line_num++;
        auto begin = std::sregex_iterator(line.begin(), line.end(), re);
        auto end_it = std::sregex_iterator();
        for (auto it = begin; it != end_it; ++it) {
            results.push_back({(*it)[1].str(), line_num});
        }
    }
    return results;
}

Document parse_file(const std::string& file_path) {
    Document doc;
    doc.file = file_path;

    // 跨平台读取文件内容（Windows 下支持中文路径）
    std::string content = read_file_content(file_path);
    if (content.empty()) {
        doc.file.clear();
        return doc;
    }

    // 按行切分
    std::vector<std::string> lines;
    std::string line;
    std::istringstream iss(content);
    while (std::getline(iss, line)) {
        lines.push_back(line);
    }

    if (lines.empty()) {
        doc.file.clear();
        return doc;
    }

    size_t pos = 0;

    // 检查 Frontmatter 开始 (---)
    if (trim(lines[0]) != "---") {
        // 无 Frontmatter，整个文件作为正文
        std::ostringstream oss;
        for (size_t i = 0; i < lines.size(); ++i) {
            oss << lines[i];
            if (i + 1 < lines.size()) oss << "\n";
        }
        doc.body = oss.str();
        return doc;
    }

    pos = 1;

    // 找 Frontmatter 结束 (---)
    size_t fm_end = lines.size();
    for (size_t i = 1; i < lines.size(); ++i) {
        if (trim(lines[i]) == "---") {
            fm_end = i;
            break;
        }
    }

    // 解析 Frontmatter
    while (pos < fm_end) {
        std::string trimmed = trim(lines[pos]);
        if (trimmed.empty()) { pos++; continue; }

        size_t colon = trimmed.find(':');
        if (colon == std::string::npos) { pos++; continue; }

        std::string key = trim(trimmed.substr(0, colon));
        std::string value = trim(trimmed.substr(colon + 1));

        if (key == "id") {
            doc.id = value;
            pos++;
        } else if (key == "title") {
            doc.title = value;
            pos++;
        } else if (key == "provides") {
            // 检查是 [a, b] 形式还是多行列表
            if (!value.empty()) {
                if (value.front() == '[') {
                    doc.provides = parse_provides_simple(value);
                    pos++;
                } else {
                    pos++;
                }
            } else {
                // 多行格式
                pos++;
                doc.provides = parse_provides(lines, pos, fm_end);
            }
        } else if (key == "prerequisite") {
            pos++;
            if (value.empty()) {
                // 多行列表
                while (pos < fm_end) {
                    std::string t = trim(lines[pos]);
                    if (t.empty()) { pos++; continue; }
                    if (t[0] != '-') break;
                    doc.prerequisite.push_back(trim(t.substr(1)));
                    pos++;
                }
            } else if (value.front() == '[') {
                doc.prerequisite = split_list(value);
            } else {
                doc.prerequisite = split_list(value);
            }
        } else if (key == "extend") {
            pos++;
            if (value.empty()) {
                while (pos < fm_end) {
                    std::string t = trim(lines[pos]);
                    if (t.empty()) { pos++; continue; }
                    if (t[0] != '-') break;
                    doc.extend.push_back(trim(t.substr(1)));
                    pos++;
                }
            } else if (value.front() == '[') {
                doc.extend = split_list(value);
            } else {
                doc.extend = split_list(value);
            }
        } else if (key == "analogy") {
            pos++;
            if (value.empty()) {
                while (pos < fm_end) {
                    std::string t = trim(lines[pos]);
                    if (t.empty()) { pos++; continue; }
                    if (t[0] != '-') break;
                    doc.analogy.push_back(trim(t.substr(1)));
                    pos++;
                }
            } else if (value.front() == '[') {
                doc.analogy = split_list(value);
            } else {
                doc.analogy = split_list(value);
            }
        } else if (key == "tags") {
            pos++;
            if (value.empty()) {
                while (pos < fm_end) {
                    std::string t = trim(lines[pos]);
                    if (t.empty()) { pos++; continue; }
                    if (t[0] != '-') break;
                    doc.tags.push_back(trim(t.substr(1)));
                    pos++;
                }
            } else if (value.front() == '[') {
                doc.tags = split_list(value);
            } else {
                doc.tags = split_list(value);
            }
        } else {
            // 未知字段，跳过
            pos++;
        }
    }

    // 如果 provides 为空，用 doc.id 作为默认 provides
    if (doc.provides.empty() && !doc.id.empty()) {
        Node n;
        n.id = doc.id;
        n.title = doc.title;
        doc.provides.push_back(n);
    }

    // Frontmatter 之后是正文
    pos = fm_end + 1;
    std::ostringstream oss;
    for (size_t i = pos; i < lines.size(); ++i) {
        oss << lines[i];
        if (i + 1 < lines.size()) oss << "\n";
    }
    doc.body = oss.str();

    // 提取 [[id]] 引用
    auto citations = extract_citations(doc.body);
    for (const auto& [id, line_num] : citations) {
        Document::Citation c;
        c.target_id = id;
        c.line = line_num;
        doc.citations.push_back(c);
    }

    // 提取 [:anchor:xxx] 锚点
    auto anchors = extract_anchors(doc.body);
    for (const auto& [id, line_num] : anchors) {
        Document::Anchor a;
        a.id = id;
        a.line = line_num;
        doc.anchors.push_back(a);
    }

    return doc;
}

} // namespace memoria
