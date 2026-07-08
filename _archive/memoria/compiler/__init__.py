"""C++ 编译器桥接：通过 subprocess 调用 memoria.exe"""
import json
import os
import subprocess
import sys
from pathlib import Path


def _find_compiler() -> str:
    """查找 memoria 编译器可执行文件"""
    # 1. 环境变量
    if env_path := os.environ.get("MEMORIA_COMPILER"):
        return env_path

    # 2. 开发态：cmake-build-debug/memoria.exe
    project_root = Path(__file__).parent.parent.parent
    candidates = [
        project_root / "cmake-build-debug" / "memoria.exe",
        project_root / "cmake-build-release" / "memoria.exe",
        project_root / "memoria.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    # 3. PATH 中查找
    import shutil
    if found := shutil.which("memoria"):
        return found

    raise FileNotFoundError(
        "memoria 编译器未找到。请先运行 cmake --build cmake-build-debug"
    )


def build(directory: str, output: str = None) -> dict:
    """
    调用 C++ 编译器构建知识库索引

    Args:
        directory: nodes/ 所在目录
        output: 输出目录（默认为 directory/../build）

    Returns:
        {"status": "ok", "stats": {...}, "warnings": [...]}
        或 {"status": "error", "message": "..."}
    """
    compiler = _find_compiler()
    cmd = [compiler, "build", "--dir", directory]
    if output:
        cmd.extend(["--output", output])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8"
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}

    # 从 stdout 最后一行解析 JSON（即使 returncode != 0 也尝试解析，
    # 因为 C++ 编译器在有 broken citations 警告时返回非 0 但仍输出 JSON）
    lines = result.stdout.strip().split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
                # 即使 returncode != 0，只要解析到 JSON 就视为成功
                # （warnings 不算错误）
                return parsed
            except json.JSONDecodeError:
                pass

    # 没解析到 JSON 才算错误
    if result.returncode != 0:
        return {"status": "error", "message": result.stderr or result.stdout}

    return {"status": "error", "message": "无法解析编译器输出"}


def check(directory: str) -> dict:
    """调用 C++ 编译器检查知识库（不构建）"""
    compiler = _find_compiler()
    cmd = [compiler, "check", "--dir", directory]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8"
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return {
        "status": "ok" if result.returncode == 0 else "error",
        "output": result.stdout,
        "errors": result.stderr,
    }


def init(directory: str) -> dict:
    """初始化新知识库"""
    compiler = _find_compiler()
    cmd = [compiler, "init", "--dir", directory]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8"
        )
    except Exception as e:
        return {"status": "error", "message": str(e)}

    return {
        "status": "ok" if result.returncode == 0 else "error",
        "output": result.stdout,
    }
