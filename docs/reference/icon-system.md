# 图标系统（Icon Pipeline）

> **一句话**：源图只放一处 `resources/icons/*.png`，跑一次 `scripts/icons/build_icons.py`，
> 多尺寸 `.ico` 与运行时图标（favicon / 顶栏 logo）自动生成并与打包配置对齐。
> **状态**：生效中，2026-09-16。脚本：`scripts/icons/build_icons.py`。

## 1. 命名约定（"指定名称即生效"）

| 你放的源图 | 生成物 | 用途 |
|---|---|---|
| `Memoria.png` | `resources/icons/Memoria.ico`（16/24/32/48/64/128/256 多尺寸）<br>`resources/icons/Memoria-big.ico`（仅 256） | 打包 exe 图标、窗口/任务栏图标 |
| 同上，且名字 = 应用图标名（默认 `Memoria`） | 追加同步到 `src/memoria/ui/static/icons/Memoria.ico` + `Memoria.png` | `index.html` 的 favicon 与顶栏 logo |
| `<其他名字>.png` | `resources/icons/<其他名字>.ico` + `-big.ico` | 预留（安装器/文档/子品牌） |

- 源图**建议正方形、边长 ≥ 256**；脚本会跳过大于源图的尺寸（不放大、不糊）
- 非正方形只告警不阻断（图标会被拉伸）
- 下划线开头的 png（`_draft.png`）视为草稿，忽略

## 2. 换应用图标的完整流程

```powershell
# 1) 用新图覆盖源图（保持文件名 Memoria.png）
Copy-Item 新图.png resources\icons\Memoria.png

# 2) 生成 ico + 同步运行时图标
python scripts\icons\build_icons.py --force

# 3) 验证：多尺寸条目、静态副本一致
python -c "import struct;b=open('resources/icons/Memoria.ico','rb').read();n=struct.unpack('<H',b[4:6])[0];print([struct.unpack('<BB',b[6+i*16:8+i*16])[0] or 256 for i in range(n)])"
```

窗口/任务栏图标在**下次启动**生效；网页 favicon 刷新即可（静态服务会自动加 `?v=` 版本号）。

## 3. 消费方（路径固定，换图不需要改这些地方）

| 消费方 | 读取路径 |
|---|---|
| `packaging/memoria.spec`（打包进 exe） | `resources/icons/Memoria.ico` |
| `memoria.app.shell.app_icon.resolve_app_icon_path()`（窗口/任务栏/WM_SETICON） | `resources/icons/Memoria.ico` → 安装目录 → 仓库根 → `static/icons/Memoria.ico` → PNG 兜底 |
| `index.html`（favicon、顶栏 `.logo-icon`） | `/icons/Memoria.ico`（= `src/memoria/ui/static/icons/`） |

## 4. 命令

| 命令 | 作用 |
|---|---|
| `python scripts/icons/build_icons.py` | 增量生成（源图没变则跳过），并同步运行时图标 |
| `--force` | 忽略时间戳强制重建（换了图但 mtime 没变时用） |
| `--check` | 只检查是否过期，过期退出码 1（提交前/CI 用） |
| `--list` | 列出会处理的源图 |

依赖：**Pillow**（仅此脚本，非运行时依赖）。缺失时脚本会提示 `pip install Pillow`。

## 4.1 透明底 logo → 圆角渐变底图标（可选一步）

原始 logo 是**透明底、两色**（深海军蓝 + 薄荷青）时，直接当图标会在两种桌面上各自糊掉一半
（深蓝在深色桌面消失、薄荷在浅色桌面发白）。用合成脚本给它加一层"自带对比"的底：

```powershell
python scripts\icons\make_tile_icon.py      # _Memoria-mark.png → Memoria.png（圆角框 + 斜向渐变 + 描边）
python scripts\icons\build_icons.py --force # 再生成 ico
```

设计要点（都在脚本顶部常量里，可命令行覆盖）：

- 渐变两端**就是图标自己的两种颜色**（`#BFEDE4` 浅薄荷 → `#0A3A66` 深海军蓝），所以
  **深蓝块落在浅端、薄荷形落在深端**，两色同时获得对比（实测 5.2:1 与 3.2:1）；
- 外框不透明 + 深色细描边 → 与桌面底色解耦（对纯白 1.8:1、对纯黑 6.5:1，轮廓都认得出）；
- 图形按裁边后的宽度取外框的 80%，四周留白即"圆角外框"，即使用到 16px 也还看得出形状。

可调：`--from/--to`（渐变两色，同时决定"哪一端深/浅"）、`--invert-mark/--no-invert-mark`
（图形内部深浅对调，默认开：深的那一色取渐变浅端色、浅的那一色取深端色）、
`--mark-ratio`（图形占比）、`--radius-ratio`（圆角）、`--margin-ratio`（留白）、
`--dx/--dy`（平移像素，正数向右/向下）、`--balance`（按 alpha 质心纠偏比例，默认 0）、
`--outline/--outline-alpha`（描边）。

图形与底色的配对规则：**交换 `--from/--to` 不会破坏对比** —— 脚本按两色的明暗关系安排
图形对调方向，始终保证"图形较浅的那部分落在较深的底色上"。

## 4.2 源图命名：哪些会被处理

`resources/icons/*.png` 里，下列文件名**自动忽略**，不生成 ico（避免草稿/备份刷出一堆文件）：

- `_` 开头（`_Memoria-mark.png`、`_draft.png`）
- 含 `copy` / `副本` / `backup` / `bak` / `orig` / `old`（如 `Memoria copy.png`、`Memoria_backup.png`）

## 4.3 手绘稿的"清杂色 / 对调配色"

手绘稿常见三类瑕疵，用 `scripts/icons/recolor_icon.py` 一次处理：

| 瑕疵 | 现象 | 处理 |
|---|---|---|
| 杂色 | 笔刷软边产生上千种过渡色 | 吸附到最近的主色（默认 4 色，见下） |
| 灰残影 | 旧合成版留下的 `#808080` 沿图形边缘 | 从四周已确定像素 BFS、取最近邻的颜色补上（**不是吸附**：吸附会把浅色区外侧刷成深色，出现深色光晕） |
| 碎点 | 孤立的小色块 | `--despeckle`（默认 30px 以下并入邻居多数色） |

**调色板必须放全"真被画上去的颜色"**——少放一个，那块实心区域就会被并进相邻色（本图标就踩过：
把 `#136EBF`/`#98BDB5` 当成过渡色，4 色塌成 2 色）。判据是**"内部占比"**：

- 实心色块 → 绝大多数像素的八邻域全是同色，内部占比 **95% 以上**
- 过渡色/灰边 → 只出现在形状边界，内部占比 **0%**

默认调色板按**明度从亮到暗**排列，`--invert` 就是整体反转它：

| 原色 | 对调后 |
|---|---|
| `#BFEDE4` 浅薄荷 | `#0F5696` 深蓝 |
| `#98BDB5` 灰绿 | `#136EBF` 亮蓝 |
| `#136EBF` 亮蓝 | `#98BDB5` 灰绿 |
| `#0F5696` 深蓝 | `#BFEDE4` 浅薄荷 |

想换配对方式，直接用 `--palette` 给出新顺序（第 i 个 ↔ 倒数第 i 个）。

```powershell
# 只清理（保持原配色）
python scripts\icons\recolor_icon.py --in resources\icons\_Memoria-drawn-20260916.png --out resources\icons\Memoria.png --force

# 清理 + 按明度对调
python scripts\icons\recolor_icon.py --in resources\icons\_Memoria-drawn-20260916.png --out resources\icons\Memoria.png --invert --force

# 每次都要接着重建 ico
python scripts\icons\build_icons.py --force
```

- 默认**保留 alpha**，只改 RGB → 半透明描边（外框最外那圈，`#072a4d` @28%）不受影响；要硬边加 `--binarize-alpha 128`
- `--invert` 只换"落到像素上的颜色"，不换"判最近色用的调色板顺序"（两个都反转 = 等于没换）
- 运行时会打印实际映射（`#bfede4 → #0f5696` 等 4 行），照着核对一眼即可
- 保留手绘原稿（`_` 开头不参与生成，如 `_Memoria-drawn-<日期>.png`），让 `--in` 指向原稿、`--out` 指向 `Memoria.png`，避免读写同一个文件
- 对比候选图放 `resources/icons/_candidates/`（同样被忽略），肉眼确认后再覆盖正式源图

## 5. 已知事项

- `.ico` 里 16–128 尺寸为 BMP 段、256 为 PNG 段（Pillow 标准行为，体积从 370KB 降到 ~74KB）；
  若打包工具报图标格式错误，改用全 BMP 编码即可。
- `Memoria-big.ico` 目前**没有消费方**（历史遗留），保留生成以免路径失效。
