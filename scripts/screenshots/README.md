# 截图采集工具（screenshots）

> 位置与口径标记（对应 `docs/conventions/readme-i18n.md` §3 截图维护规则）。

## 用途

给 `resources/screenshots/` 拍 **README / 文档演示图**：由人把界面切到要拍的样子，
每切一次按一下热键抓一张，脚本按预设顺序命名落盘。

选它而不是系统截图工具的两个理由：

1. **只抓应用窗口客户区**（不含标题栏 / 桌面），尺寸稳定 —— 符合 `readme-i18n.md` §3.1 的分辨率基线 1536×816。
2. **重复帧识别**：切页面没生效 / 连着按两下时，画面与上一张几乎相同 → 播错误音、不占号、不覆盖旧文件，
   避免"拍到的还是上一页"污染素材。

## 用法

```powershell
# 默认：抓 5 张 README 演示图到 resources/screenshots/，按 F9 依次拍摄
python scripts\screenshots\hotkey_capture.py

# 指定文件与顺序（这里只拍一张：去重参照物改为磁盘上已有的同名文件）
python scripts\screenshots\hotkey_capture.py --names demo-graph-2d.png

# 拍别人的窗口 / 换触发键 / 关掉去重
python scripts\screenshots\hotkey_capture.py --out artifacts\shots --title Notepad --key F8 --dup-rms 0
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--out` | `resources/screenshots/` | 输出目录（默认按仓库根解析，可在任意 cwd 运行） |
| `--names` | 5 张 `demo-*.png` | 逗号分隔，**按拍摄顺序**落盘 |
| `--key` | `F9` | `F1`–`F24` 或键码（`0x78`） |
| `--title` | `Memoria` | 窗口标题需包含的字符串；**以该串开头的窗口优先** |
| `--pid` | 自动 | 按进程号定位（给了就不看标题） |
| `--dup-rms` | `3.0` | 重复帧阈值（16×16 亮度指纹 RMS）；`0` = 关闭去重 |
| 提示音 | — | 成功 = `Windows Notify.wav`；重复帧 = `Windows Critical Stop.wav` |

## 使用前提与边界

- **窗口必须在最前**：抓的是屏幕像素（`CopyFromScreen` 语义），窗口被遮挡会拍到遮挡物。
  脚本按 `--title` / `--pid` 找窗口，找不到时提示但仍继续等下一次按键。
- **要在交互式终端里跑**：它是个前台循环，靠 `GetAsyncKeyState` 轮询热键，等了多久就等多久（`Ctrl+C` 退出）。
  输出按行缓冲，重定向到文件时看不到实时进度加 `python -u`。
- **仅 Windows**：依赖 `user32` / `winsound`；非 Windows 直接报错退出。
- **依赖 Pillow**（仅本脚本，非运行时依赖）：缺失时提示 `pip install Pillow`。
- 抓图**只覆盖应用窗口客户区**，不含窗口管理器装饰 / 任务栏；多显示器取窗口所在屏的区域。

## 相关

- 收录规则与分辨率基线：`docs/conventions/readme-i18n.md` §3
- 截图存放地：`resources/screenshots/`（见 `resources/README.md`）
