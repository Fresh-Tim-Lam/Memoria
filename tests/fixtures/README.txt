Memoria 测试知识库（fixtures）说明
================================

本目录下每个子文件夹（如 m3_integrity_kb）都是一份**独立的知识库**，
不是把整个 tests/ 当作一个库。

标准知识库目录结构（与 examples/ 相同）
--------------------------------------

  my-kb/
    *.md                 文档（用户编辑的正文）
    .memoria/            Memoria 元数据目录（程序自动维护）
      manifest.yaml      文件清单（打开库时建立/更新）
      sidecars/          各 md 的配置（知识点、链接等）
        foo.memoria.yaml
      pending.yaml       （计划中）待确认提议
      cache/             （可选）可重建缓存
    .build/              （可选）构建临时文件，可删除

为何有些 fixture 里看不到 .memoria？
----------------------------------

  - m3_create_kb / 新建的库：只有 .md，首次「打开」后程序会创建 .memoria/
  - m3_integrity_kb / m3_rename_kb：已带 .memoria/sidecars/ 用于固定测试场景
  - tests/ 根目录**不会**出现 .memoria —— 它不是知识库，只是测试数据容器

手测时请「打开」具体子目录，例如：
  tests/fixtures/m3_integrity_kb
