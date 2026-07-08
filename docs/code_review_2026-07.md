# 全工程代码审查报告(2026-07)

三路并行审查:核心求解/几何/工作流、GUI、工程基建(CI/打包/文档/
仓库卫生)。共约 40 条发现,按 P0(关键缺陷)/P1(重要)/P2(打磨)
分档。**P0+P1 已在本次整改中落地**(见文末"整改结果");P2 未整改,
留作后续候选。

## 审查正面结论(无需动作)

- Linux CI(`ci.yml`)存在且每次 push/PR 跑全量 pytest,DEVSIM/gmsh
  从 PyPI wheel 安装、真实求解在 CI 中执行;
- help 文档/图/图标正确打进 wheel(`package-data`)与两种 Windows 包
  (PyInstaller `collect_data_files` / Nuitka `--include-package-data`);
  `configs/` 由两条 workflow 显式拷入(带存在性 guard);
- git 仓库无大文件问题(size-pack ~7 MiB,最大 blob 是 ~240 KB 文档
  图;`*.msh`/`results/` 正确忽略);
- 入口点/extras(`[dev]`/`[gui]`/`[viz]`)完整;`fresh_devsim`
  fixture 正确重置 DEVSIM 全局态;测试合理使用 `importorskip` 降级;
- PROJECT_DEV_PLAN 统计与实际几乎一致(行数/配置数精确)。

## P0 — 关键缺陷(已修复)

| # | 位置 | 问题 | 修复 |
|---|------|------|------|
| 1 | `workflow/runner.py` | 全部实验都在偏置循环结束后才写 CSV;中途 `ConvergenceError` 丢弃**所有**已算点(含已完成的整条曲线) | `_sweep` 把已完成点挂到异常上;五个 run_* 统一经 `_flush_partial` 落盘部分 CSV 再重抛 |
| 2 | `gui/run_queue.py` | QProcess 无 `errorOccurred` 处理:CLI 起不来时永不发 `finished`,行卡 running、并行槽泄漏 | `_on_proc_error` 处理 FailedToStart:标 failed、释放槽、发失败信号;`_touch`/`row_of` 对已移除实验 no-op |
| 3 | `gui/main_window.py` closeEvent | 关窗不停止在跑求解 → 僵尸进程 | 有活动任务先确认;`RunQueue.shutdown()` kill + waitForFinished |
| 4 | `workflow/config.py`、`geometry/params.py` | `vg_step/vd_step=0`、`vtk_stride=0` 深处 ZeroDivisionError;空 `vd`/`vg` 列表晚期报错;`icrit_a<=0` 产出 nan FOM;坏值报错不带 section 名;未知 sim type 静默跑 idvd | 全部前置验证;`_build` 同时包 ValueError 加 section 前缀;dispatcher 显式映射,未知类型 raise |
| 5 | `pyproject.toml` / `__init__.py` | v0.5.1 tag 已发但两处版本号都还是 "0.5",且双源易漂移 | `[tool.setuptools.dynamic]` 从 `__init__.__version__` 单源;bump 0.5.2 |

## P1 — 重要改进(已落地)

| # | 位置 | 问题 | 改进 |
|---|------|------|------|
| 6 | `gui/run_queue.py` + main_window | 运行失败只有红格+一行日志(STEP 转换却有弹窗) | RunQueue 保留输出尾部(30 行),`experiment_failed` 信号 → 弹窗显示尾部;structure 预览失败同样弹窗;转换/预览进程补 `errorOccurred` + `deleteLater` |
| 7 | `workflow/config.py` | sim type ↔ structure 不匹配要等 build_mesh 之后才被拦截 | `check_sim_structure` 在 `Runner.run()` 一开始(建网格前)校验;external 结构仍留给接触名运行时校验(structure 预览合法搭配默认类型,故不在 load 时强制) |
| 8 | `geometry/params.py` | `n_sheets`(理想倍乘)与 `n_fins`/`n_stacked_sheets`(真实网格复制)可同设 → 电流静默 9× | `_validate_replication` 拒绝共存 |
| 9 | tests/ | `run_idvd`/`run_cfet_idvg`/`run_cfet_idvd`/`run_cfet_vtc` 零端到端覆盖;不收敛路径未测;GUI live QProcess 路径(成功/失败/起不来)未测 | 新增 `tests/test_experiments_e2e.py`(6 个)+ test_gui.py 5 个 live 测试 + test_config.py 5 个验证测试 |
| 10 | README | STEP 导入完全未提;无 cfet_idvd;GUI 段落还是旧 Tab 界面;目录/测试描述过期 | 全部刷新;新增 `configs/cfet_idvd_2d.yaml` 示例 |

## P2 — 打磨项(本次未整改,后续候选)

**核心求解/物理**
- runner 五个实验的 measure/tick/VTK 循环与 CSV/plot/JSON 尾块仍有
  复制(部分保存修复后重复度略降);`run_cfet_idvd` 不写 VTK
  (`output.vtk` 对它是静默 no-op)
- `n_i` 不随温度重算(T≠300K 时热力学不一致;SiGe 路径已有同款
  T^1.5·exp(-Eg/2kT) 算式可复用);高掺杂无 BGN/Fermi-Dirac
- 自适应斜坡步长失败后不回涨;DG/CVT homotopy 阶梯硬编码
- 无网格缓存(纯物理参数 sweep 每点重复跑 gmsh);串行 sweep 每点
  新建进程池;sweep 无 resume(断点续跑)
- 按 sim type 提示被忽略的偏置字段(idvg 设了 vd_start 等)
- `mobility.py` "lombardi_vsat (2D only)" 注释过期(3D 已实现)

**GUI**
- 实验表/窗口几何/分栏位置不持久化(无 QSettings)
- VTK/网格加载在 GUI 线程(大网格卡界面);STEP discover 同步执行
- 无键盘快捷键;无拖放;无"查看该 run 实际用的 config"入口
- Sweep 对话框把 `max_parallel` 当全局副作用改掉
- 输出目录时间戳只有 `%H%M%S`(同秒重跑可碰撞)
- `StructureView` 不主动 close plotter;main_window 拆分
  (ConfigBrowser/ProcessController);SweepDialog 应独立成文件
- GUI chrome 英文硬编码(无 QTranslator;双语目前只到 Help 文档)

**工程**
- 依赖无下界/上界(numpy ABI 风险);`configs/` 不进 wheel(pip 安装
  的 quickstart 跑不通,需 git checkout;或移入包数据)
- 无 CHANGELOG;无 coverage 度量;CI 可加 `-m "not slow"` 快车道
- `.step` 演示件是 187 KB 二进制入库(可接受,已有再生脚本)

## 整改结果

P0+P1 全部落地于提交 `docs/dev_plan_code_review_p0p1.md` 所记的
commit;测试 120 → 136,全量绿(含 4 个新慢速端到端)。
