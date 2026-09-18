# Memoria {version} — Windows 发布包

双击运行：

  Memoria.exe

同目录还需要保留（不可单独拷贝 exe）：

  lib/              程序依赖
  resources/        示例知识库、图标、内置 Agent 整理提示词（agent-prompts/）、格式说明（docs/）

首次运行后自动生成：

  config/           程序设置（ui-settings.json）

系统要求：

  Windows 10/11 x64；.NET Framework 4.7.2+ 与 WebView2 运行时
  （Windows 10 1803+ / Windows 11 已内置）

启动失败怎么办：

  1) 确认是**整包解压**到可写目录后再运行的（不要直接在 zip 里双击 exe）；
  2) 失败时 exe 同目录会生成 crash.log，先看其中的报错信息；
  3) 若仍起不来，在解压目录执行一次下面的命令（解除 Windows 给下载文件加的
     「来自网络」标记），然后重试：

       Get-ChildItem -Recurse | Unblock-File
