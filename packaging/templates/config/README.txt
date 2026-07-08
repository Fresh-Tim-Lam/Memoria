Memoria 程序设置目录
====================

本目录与 Memoria.exe 同级，用于保存用户偏好（便携，可随文件夹一起拷贝）。

  ui-settings.json   界面设置（图谱、搜索、检查、上次打开的知识库等）

首次保存设置后自动生成 ui-settings.json。
知识库数据仍在各知识库目录下的 .memoria/ 中，不会写进本目录。

如需重置界面设置：关闭程序后删除 ui-settings.json 即可。

高级：可通过环境变量 MEMORIA_CONFIG_DIR 指定其它配置目录。
