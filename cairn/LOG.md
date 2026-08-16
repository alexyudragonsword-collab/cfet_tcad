# Project Cairn 日志

本文件按倒序记录实质性进展——最新条目置于本行正下方。每条保持简短，只写摘要与指针；结论沉淀进 `cairn/<topic>.md`。

## 2026-08-16 · Project Cairn 初始化

- 完成 Project Cairn 结构初始化：`AGENTS.md`、`CLAUDE.md`、`.cairn/config.yaml`、`cairn/LOG.md`、`cairn/ROADMAP.md`。
- 配置：`git_policy: track`（本仓库公开，知识笔记随仓库走，与既有 `docs/` 归档一致）、provider 暂缓对接、文档语言中文。
- **既有 `CLAUDE.md` 的 49 行长期约定已迁入 `AGENTS.md`**（plan-mode 归档制度、Windows 工作流仅手动触发、提交尾注格式、分支策略），`CLAUDE.md` 改为一行 `@AGENTS.md` 存根。原文件已备份，内容零丢失。
- 历史知识按 `inventory_only` 登记，未改写原文：见 `cairn/历史知识清单.md`。
- 详见 `AGENTS.md` 与 `.cairn/config.yaml`。

## 2026-08-16 · Windows 包体积裁剪 209 MB + 文档补齐

- 依据 CI 实测明细（解包 1.3 GB：MKL 539 MB / VTK 314 MB / gmsh 172 MB）做了两刀有确凿依据的裁剪：gmsh DLL 去重 -86 MB、MKL 不可达 DLL -123 MB；CPU 分派变体全部保留。
- 两条打包跑道均加了必需 DLL 断言，裁错让构建失败而非产出"能启动、一求解就死"的包。
- 补齐文档缺口：新增 `CHANGELOG.md`、归档计划 25、刷新主计划漂移的统计数字。
- 落地提交 `ed0ee0e`；详见 `docs/dev_plan_windows_exe_size.md`。
- **待验证**：裁剪后尚未跑过 Windows 构建，需手动触发两条 workflow 确认冻结冒烟全绿。
