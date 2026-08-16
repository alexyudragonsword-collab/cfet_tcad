# STACKED CMOS TCAD 路线图

**当前重点**：验证 Windows 包体积裁剪（提交 `ed0ee0e`）——需手动触发两条打包 workflow，确认冻结冒烟全绿、体积确实下降约 209 MB。

## 里程碑

- [ ] 验证已落地的体积裁剪：手动触发 `windows-exe.yml` / `windows-nuitka.yml`，核对诊断步骤输出的新明细
- [ ] VTK 体积裁剪（独立一轮）：把 `collect_all(vtkmodules)` 换成按 pyvista 实际用到的子模块精选列表，目标 314 MB 中的大部分；风险高于已做的两刀，需可回滚的独立提交
- [ ] LLM 参数优化器的真实 API 端到端验证：本地设 `ANTHROPIC_API_KEY` 跑一次真实器件优化（如 `configs/nsheet_nfet_2d.yaml`，目标"maximize ion_ioff_ratio, constrain ss_mv_per_dec < 75"）
- [ ] 与 Sentaurus 的量化对标验证：关键器件结果的数值比对
- [ ] 扩充工艺角与物理模型，覆盖更多器件场景

## 开放问题

1. `docs/DEV_PLANS_ARCHIVE.md` 已 138 KB 且标题层级不一致，检索性下降——是否统一编号或拆分？
2. 是否补齐面向二次开发者的 API 参考文档？相关：公开函数 docstring 覆盖率 45%，`geometry` / `optimize` 仅 28%，而这两块最可能被二次开发。
3. 项目从未打过 git tag，`CHANGELOG.md` 的 0.1.0 / 0.5 两节是回溯整理的——是否补打历史 tag，或从 0.5.2 起正式启用 tag？
