cmake_minimum_required(VERSION 3.15)
project(memoria CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 编译器选项
if(MSVC)
    add_compile_options(/W4 /EHsc)
else()
    add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# 可执行文件: memoria (编译器 CLI)
add_executable(memoria
    src/main.cpp
    src/scanner.cpp
    src/parser.cpp
    src/validator.cpp
    src/builder.cpp
)

target_include_directories(memoria PRIVATE src)
