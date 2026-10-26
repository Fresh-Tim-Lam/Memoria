"""读 PE 头 OptionalHeader.Subsystem：证明 `Package/Memoria.exe` 是 GUI 子系统（无控制台）。

Image Subsystem 取值：
  2 = IMAGE_SUBSYSTEM_WINDOWS_GUI  （无控制台）
  3 = IMAGE_SUBSYSTEM_WINDOWS_CUI  （控制台应用）

用法（仓库根目录）：
    python artifacts/agent/verify/todo/console-flash-fix/pe_subsystem.py
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
_SUBSYSTEM_NAMES = {2: "IMAGE_SUBSYSTEM_WINDOWS_GUI", 3: "IMAGE_SUBSYSTEM_WINDOWS_CUI"}


def read_pe_subsystem(path: Path) -> dict:
    data = path.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError(f"{path} 不是 MZ/PE 文件")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        raise ValueError(f"{path} 缺 PE 签名")
    coff = e_lfanew + 4
    optional_size = struct.unpack_from("<H", data, coff + 16)[0]
    optional = coff + 20
    magic = struct.unpack_from("<H", data, optional)[0]
    # PE32(0x10B) / PE32+(0x20B) 的 Subsystem 都在 OptionalHeader 偏移 68
    subsystem = struct.unpack_from("<H", data, optional + 68)[0]
    return {
        "path": str(path),
        "pe_magic": hex(magic),
        "optional_header_size": optional_size,
        "subsystem": subsystem,
        "subsystem_name": _SUBSYSTEM_NAMES.get(subsystem, f"UNKNOWN({subsystem})"),
        "has_console": subsystem == 3,
    }


def main() -> int:
    targets = {
        "packaged_memoria_exe": REPO / "Package" / "Memoria.exe",
        "python_cui": Path(sys.executable),
        "pythonw_gui": Path(sys.executable).with_name("pythonw.exe"),
    }
    out: dict = {"targets": {}}
    for key, path in targets.items():
        if not path.is_file():
            out["targets"][key] = {"path": str(path), "error": "not found"}
            continue
        try:
            out["targets"][key] = read_pe_subsystem(path)
        except Exception as exc:  # noqa: BLE001
            out["targets"][key] = {"path": str(path), "error": repr(exc)}
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
