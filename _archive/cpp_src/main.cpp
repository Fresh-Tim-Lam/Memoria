#include <iostream>
#include <fstream>
#include <filesystem>
#include <string>
#include <vector>

#include "scanner.h"
#include "parser.h"
#include "validator.h"
#include "builder.h"

// 简单 JSON 输出辅助
static void print_json_result(const memoria::BuildResult& r) {
    std::cout << "{";
    std::cout << "\"status\": \"ok\", ";
    std::cout << "\"stats\": {";
    std::cout << "\"nodes\": " << r.node_count << ", ";
    std::cout << "\"relations\": " << r.relation_count << ", ";
    std::cout << "\"citations\": " << r.citation_count << ", ";
    std::cout << "\"anchors\": " << r.anchor_count << ", ";
    std::cout << "\"files\": " << r.file_count;
    std::cout << "}, ";
    std::cout << "\"warnings\": [";
    for (size_t i = 0; i < r.warnings.size(); ++i) {
        if (i > 0) std::cout << ", ";
        std::cout << "\"" << r.warnings[i] << "\"";
    }
    std::cout << "]}";
    std::cout << std::endl;
}

static void print_usage() {
    std::cerr << "Usage: memoria <command> [options]\n\n"
              << "Commands:\n"
              << "  build --dir <path> [--output <path>]   Build knowledge base index\n"
              << "  check --dir <path>                     Check without building\n"
              << "  init --dir <path>                      Initialize a new knowledge base\n"
              << "  --help                                 Show this help\n";
}

static int cmd_build(const std::string& dir, const std::string& output) {
    // 扫描根目录下所有 .md，但排除程序专用目录 .build/
    auto files = memoria::scan_directory(dir, {".build"});
    if (files.empty()) {
        std::cerr << "Error: no .md files found in " << dir << std::endl;
        std::cerr << "Hint: 直接把 .md 文件放在知识库根目录或任意子目录下" << std::endl;
        return 1;
    }
    std::cerr << "[memoria] Scanned " << files.size() << " .md files from " << dir << std::endl;

    // 2. 解析
    std::vector<memoria::Document> docs;
    for (const auto& file : files) {
        auto doc = memoria::parse_file(file);
        if (doc.file.empty()) {
            std::cerr << "[memoria] Warning: failed to parse " << file << std::endl;
            continue;
        }
        docs.push_back(doc);
    }
    std::cerr << "[memoria] Parsed " << docs.size() << " documents" << std::endl;

    // 3. 验证
    auto validation = memoria::validate(docs);
    if (!validation.broken_citations.empty()) {
        std::cerr << "[memoria] Broken citations:" << std::endl;
        for (const auto& c : validation.broken_citations) {
            std::cerr << "  - " << c << std::endl;
        }
    }
    if (!validation.cycles.empty()) {
        std::cerr << "[memoria] Cycles detected:" << std::endl;
        for (const auto& cycle : validation.cycles) {
            std::cerr << "  - ";
            for (size_t i = 0; i < cycle.size(); ++i) {
                if (i > 0) std::cerr << " -> ";
                std::cerr << cycle[i];
            }
            std::cerr << std::endl;
        }
    }
    if (validation.ok()) {
        std::cerr << "[memoria] Validation passed" << std::endl;
    }

    // 4. 构建（默认输出到 dir/.build）
    std::string out_dir = output.empty() ? (dir + "/.build") : output;
    auto result = memoria::build(docs, validation, out_dir);
    std::cerr << "[memoria] Built: " << result.node_count << " nodes, "
              << result.relation_count << " relations" << std::endl;

    // 5. 输出 JSON 结果（供 Python 调用解析）
    print_json_result(result);
    return 0;
}

static int cmd_check(const std::string& dir) {
    auto files = memoria::scan_directory(dir, {".build"});
    if (files.empty()) {
        std::cerr << "Error: no .md files found in " << dir << std::endl;
        return 1;
    }

    std::vector<memoria::Document> docs;
    for (const auto& file : files) {
        auto doc = memoria::parse_file(file);
        if (!doc.file.empty()) docs.push_back(doc);
    }

    auto validation = memoria::validate(docs);

    int errors = 0;
    if (!validation.broken_citations.empty()) {
        std::cout << "Broken citations (" << validation.broken_citations.size() << "):" << std::endl;
        for (const auto& c : validation.broken_citations) {
            std::cout << "  [ERROR] " << c << std::endl;
            errors++;
        }
    }
    if (!validation.cycles.empty()) {
        std::cout << "Cycles (" << validation.cycles.size() << "):" << std::endl;
        for (const auto& cycle : validation.cycles) {
            std::cout << "  [ERROR] ";
            for (size_t i = 0; i < cycle.size(); ++i) {
                if (i > 0) std::cout << " -> ";
                std::cout << cycle[i];
            }
            std::cout << std::endl;
            errors++;
        }
    }
    if (!validation.orphan_nodes.empty()) {
        std::cout << "Orphan nodes (" << validation.orphan_nodes.size() << "):" << std::endl;
        for (const auto& n : validation.orphan_nodes) {
            std::cout << "  [WARN] " << n << std::endl;
        }
    }

    if (errors == 0) {
        std::cout << "OK: " << docs.size() << " documents, "
                  << validation.orphan_nodes.size() << " orphan(s)" << std::endl;
        return 0;
    }
    return 1;
}

static int cmd_init(const std::string& dir) {
    namespace fs = std::filesystem;
    fs::create_directories(dir);
    fs::create_directories(dir + "/.build");

    // 写示例文件（直接放根目录）
    std::ofstream(dir + "/hello.md") <<
        "---\n"
        "id: hello\n"
        "title: Hello Memoria\n"
        "provides:\n"
        "  - id: hello\n"
        "    title: Hello Memoria\n"
        "    anchor: intro\n"
        "prerequisite: []\n"
        "extend: []\n"
        "tags: [example]\n"
        "---\n\n"
        "## 简介 [:anchor:intro]\n\n"
        "欢迎来到 Memoria！这是一个知识库示例文件。\n";

    std::cout << "Initialized Memoria knowledge base at " << dir << std::endl;
    std::cout << "Next step: 把你的 .md 知识文件放在 " << dir << " 下任意位置" << std::endl;
    return 0;
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        print_usage();
        return 1;
    }

    std::string command = argv[1];

    if (command == "--help" || command == "-h") {
        print_usage();
        return 0;
    }

    // 解析参数
    std::string dir, output;
    for (int i = 2; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--dir" && i + 1 < argc) {
            dir = argv[++i];
        } else if (arg == "--output" && i + 1 < argc) {
            output = argv[++i];
        }
    }

    if (command == "build") {
        if (dir.empty()) { std::cerr << "Error: --dir required" << std::endl; return 1; }
        return cmd_build(dir, output);
    } else if (command == "check") {
        if (dir.empty()) { std::cerr << "Error: --dir required" << std::endl; return 1; }
        return cmd_check(dir);
    } else if (command == "init") {
        if (dir.empty()) { std::cerr << "Error: --dir required" << std::endl; return 1; }
        return cmd_init(dir);
    }

    std::cerr << "Unknown command: " << command << std::endl;
    print_usage();
    return 1;
}
