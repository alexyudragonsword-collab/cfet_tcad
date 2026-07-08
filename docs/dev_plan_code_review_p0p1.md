# 工程审查整改:P0 关键缺陷 + P1 重要改进

## Context

对全工程(核心求解 / GUI / 基建)做了三路并行审查,共约 40 条发现。
用户选定整改 **P0+P1** 档:修复关键缺陷、补齐 CFET 端到端测试、刷新
README。P2 打磨项(网格缓存、实验表持久化、runner 去重、快捷键、
i18n 等)本次不做,留在报告结论里备查。

审查正面结论(不需要动):Linux CI 已存在且每次 push 跑全量 pytest;
help 文档/图/configs 均正确打进 wheel 与两种 Windows 包;git 仓库无大
文件问题;PROJECT_DEV_PLAN 统计基本准确。

## P0 — 关键缺陷修复

### 1. 中途不收敛丢失全部已算数据(runner.py)
现状:`run_idvg`/`run_idvd`/`run_cfet_idvg`/`run_cfet_idvd` 都在全部
偏置循环结束后才写 CSV/PNG/JSON;任何一点 `ConvergenceError` 抛出即
丢弃所有已测数据(如 `src/cfet_tcad/workflow/runner.py:201-204`)。
改法:每个实验的偏置循环包 `try/except ConvergenceError`,异常时把
已收集的 rows 落盘(部分 CSV + 日志注明中断点)再重新抛出。四个
run_* 用同一个小 helper(如 `_flush_partial(name, rows, ...)`)。

### 2. GUI QProcess 启动失败无处理 → 行永久 running、槽位泄漏
三处 QProcess(`run_queue.py:170-185` 求解、`main_window.py`
`convert_step_file` / `preview_structure`)都没连 `errorOccurred`;
CLI 起不来时 Qt 不发 `finished`,实验卡在 running 永久占用并行槽。
改法:三处都连 `proc.errorOccurred` → 标记 failed、释放槽、写日志。
顺手加固 `run_queue.py:166` `_touch`/`row_of`:实验已从 model 移除时
no-op 而不是 `ValueError` 崩溃。

### 3. closeEvent 不停止运行中的求解 → 僵尸进程
`main_window.py:647-650` 只关 help 窗口。改法:有 running/queued 任务
时弹确认框;确认后 `self.queue.stop_all()` 再接受关闭。

### 4. 配置验证缺口(config.py + runner.py)
- `vtk_stride >= 1`、`vg_step`/`vd_step != 0`(现在深处
  `ZeroDivisionError`);
- 当前 sim type 用到的 `vd`/`vg` 列表非空;
- `icrit_a > 0`(负值产生 nan FOM);
- `_build`(config.py:103)同时捕 `ValueError` 并前缀 section 名
  (现在坏值报错不带上下文);
- `runner.run()` 的 if-ladder 末尾显式 `type == "idvd"`,未知类型
  raise 而非静默跑 idvd。

### 5. 版本号单源化 + 补 bump
v0.5.1 标签已存在但 pyproject 与 `__init__.__version__` 都还是 "0.5"。
改法:pyproject 用 `[tool.setuptools.dynamic]` 从
`cfet_tcad.__version__` 读版本;`__init__.py` bump 到 `0.5.2`(下个
发布号)。About 对话框自动跟随。

## P1 — 重要改进

### 6. 运行失败弹窗(与 STEP 转换一致)
`run_queue.py` `_on_finished` 非零退出目前只有红格 + 一行日志。改法:
RunQueue 为每个运行保留输出尾部(最后 ~30 行),新增
`experiment_failed(exp, tail)` 信号;MainWindow 弹 QMessageBox 显示尾
部(镜像 `_step_converted` 的做法)。`preview_structure` 失败同样弹窗。

### 7. type↔structure 在建网格前交叉验证
`_validate_sim_contacts` 现在在 build_mesh 之后才拦截。在
`build_config` 时即校验:`cfet_*` 类型 + `nanosheet_2d`/`gaa_3d` 结构
→ 报错;`idvg`/`idvd` + `cfet_2d`/`cfet_3d` → 报错;`external` 跳过
(留给现有运行时接触验证)。

### 8. n_sheets 与几何复制双重计数校验
`params.py` `_validate_replication`:`n_fins>1` 或 `n_stacked_sheets>1`
时拒绝 `n_sheets != 1`(现在会静默 9× 电流)。

### 9. 端到端冒烟测试补齐(tests/)
- `run_idvd`、`run_cfet_idvg`、`run_cfet_idvd`、`run_cfet_vtc` 各加一个
  粗网格 2D 冒烟测试(断言 CSV 存在、曲线单调/非空、FOM 合理),
  慢的标 `@pytest.mark.slow`;
- 不收敛部分保存测试:构造必然不收敛的偏置(极小 `min_step`),断言
  抛 `ConvergenceError` 且部分 CSV 已落盘(覆盖 P0-1);
- GUI live 路径测试:monkeypatch `cli_command` 为
  `python -c "print @@PROGRESS...; exit 0/1"` 的假 CLI,覆盖
  `_start`/`_on_output`/`_on_finished` 成功与失败路径;再用不存在的
  可执行文件覆盖 `errorOccurred` 路径(覆盖 P0-2);
- 新增配置验证的单测(零步长/空列表/icrit/type↔structure/
  n_sheets 冲突各一条)。

### 10. README 刷新
- 新增 STEP 导入小节(demo `.step`、右键 Convert、`import-step` CLI);
- 仿真类型清单补 `cfet_idvd`;
- GUI 小节(README.md:129-149)重写为单窗口布局(实验表 + 行内按钮 +
  Results/Structure 分区 + 双击弹参数编辑);
- 刷新过期的目录说明、测试数量与运行时长描述。

### 11. 文档收尾(CLAUDE.md 约定)
- 完整审查报告落盘 `docs/code_review_2026-07.md`(含未整改的 P2 清单,
  供以后参考);
- 本计划归档 `docs/dev_plan_code_review_p0p1.md` + 追加
  `docs/DEV_PLANS_ARCHIVE.md`;
- `docs/PROJECT_DEV_PLAN.md`:更新头部提交号、清掉已完成 TODO、刷新
  统计(行数/测试数/提交数)、Phase 9 加一行。

## 关键文件

- `src/cfet_tcad/workflow/runner.py`(部分保存、dispatcher、验证时点)
- `src/cfet_tcad/workflow/config.py`(验证、_build 包装)
- `src/cfet_tcad/geometry/params.py`(n_sheets 校验)
- `src/cfet_tcad/gui/run_queue.py`(errorOccurred、尾部缓冲、failed 信号、_touch 加固)
- `src/cfet_tcad/gui/main_window.py`(closeEvent、失败弹窗、preview/convert errorOccurred)
- `pyproject.toml` + `src/cfet_tcad/__init__.py`(版本单源化)
- `tests/test_solve_smoke.py`/`test_gui.py`/`test_config.py` + 新增测试
- `README.md`、`docs/*`

## 验证

1. 全量 `pytest`(预计 120 → ~135+),重点新增测试全绿;
2. 手动:构造不收敛配置跑 `cfet-tcad run`,确认部分 CSV 落盘且报错
   信息清晰;
3. xvfb GUI 冒烟:假 CLI 失败路径确认红格 + 弹窗 + 槽位释放;
4. `pip install -e .` 后 `python -c "import cfet_tcad; print(cfet_tcad.__version__)"`
   与 `pip show` 版本一致(单源化生效);
5. 提交推送 feature 分支;main 合并与 Windows 打包触发按惯例等用户
   确认/手动操作。

## 明确不做(P2,记录在报告里)

网格缓存、sweep resume、实验表/窗口几何持久化、runner 扫描循环去重
(F1-F3)、n_i(T)/BGN 物理增强、main_window 拆分、Qt i18n、键盘快捷
键、CHANGELOG、coverage、依赖版本下界、configs 进 wheel。

## 结果

按计划全部落地,一次到位:

- runner:`_sweep` 把已完成点挂到 `ConvergenceError` 上,五个实验
  统一 `_flush_partial` 落盘部分 CSV;dispatcher 显式映射,未知类型
  raise;`check_sim_structure` 移到 `Runner.run()`(计划原定
  build_config 时校验,实测会挡掉"CFET 结构 + 默认 idvg"的
  structure 预览合法用法,故放到建网格前的运行入口);
- config/params:零步长、vtk_stride、空偏置列表、icrit_a、section
  前缀包装、n_sheets 互斥全部生效,21 个 shipped 配置全部通过;
- GUI:`errorOccurred`(FailedToStart)释放槽位 + 失败信号、
  `_touch` 对已删行 no-op、`shutdown()` kill+wait、关窗确认、
  运行失败弹窗(输出尾部 30 行)、convert/preview 同样处理 +
  deleteLater;
- 版本 0.5.2 动态单源(`[tool.setuptools.dynamic]`),pip show 与
  模块一致;
- 测试 120 → 136:e2e 6 个(idvd/cfet_idvg/cfet_idvd/cfet_vtc/
  部分保存/未知类型)、GUI live 5 个(成功/失败/起不来/删行/关窗,
  发现并修复了测试间 deleteLater 悬空的 SIGBUS)、config 5 个;
  新增 `configs/cfet_idvd_2d.yaml` 示例;
- README:STEP 导入小节、cfet_idvd、单窗口 GUI 重写、目录/测试
  描述刷新;审查报告 `docs/code_review_2026-07.md`(含 P2 备查)。

落地于提交(见 git log "Project review hardening" 附近):全量
pytest 136 绿。
