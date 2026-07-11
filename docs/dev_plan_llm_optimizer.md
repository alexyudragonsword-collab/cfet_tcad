# LLM 器件参数优化器(GUI 直接集成)

## Context

用户提出"外挂一个 LLM 对已有器件做参数优化,并在程序环境中验证结果",
并要求先分析同类工作 AgenticTCAD(arXiv 2512.23742,DATE 2026,
`github.com/guangxifan/llm4tcad_flow`)再决定是否往这个方向演进。

论文分析结论:AgenticTCAD 一半工作量花在"让 LLM 可靠生成 Sentaurus
SDE/SDevice 脚本"上(为此专门造数据集+微调模型),因为 Sentaurus
是类 TCL 脚本、无结构化校验。本工程已经有一层类型化、带
`__post_init__` 校验的 YAML/dataclass 配置层(`apply_overrides` +
`build_config`),LLM 只需吐一个 dotted-path 参数字典就能被仿真前
校验,天然绕开了论文最难的部分。AgenticTCAD 是单点串行 25 轮收敛
(2nm nanosheet FET,4.2 小时 vs 人工 7.1 天);本工程已有的
`multiprocessing`/进程隔离并行仿真基础设施(`sweep.py`、
`run_queue.py`)支持"每轮批量候选并行验证",在墙钟收敛速度上是对
论文架构的潜在改进。

结论:可以往这个方向演进,且起点结构性地优于 AgenticTCAD。以下是
经过 Explore+Plan 双轮调研、并与用户确认全部关键设计决策后的落地
方案。

## 用户已确认的设计决策

1. **优化循环形态**:批量候选 + 并行验证——LLM 每轮基于历史一次性
   提出 N 组候选参数,复用现有多进程隔离基础设施并行跑完,结果整体
   喂回 LLM 做下一轮。
2. **LLM 接入方式**:可插拔多厂商适配器接口(`LLMProvider` 抽象),
   不锁定单一厂商;首个具体实现用 Claude API(`anthropic` SDK)。
3. **落地范围**:直接做 GUI 集成,不做 CLI 过渡阶段。
4. **目标函数**:无强烈偏好→采用可扩展默认设计(有序
   `{metric, direction, constraint}` 列表,归一化加权评分供排序,
   但 LLM 上下文里始终看到完整原始 FOM 而非只看标量分数)。
5. **监控对话框**:非模态(`.show()`),因为一次优化可能持续多轮
   /多分钟,不应卡住主窗口——这是对现有对话框都用 `.exec()` 同步
   模态这一惯例的刻意偏离。
6. **可调参数默认清单**:只含几何/掺杂/功函数/迁移率标定因子等真正
   影响器件物理的参数,**不含网格密度**(`nx_sd`/`nx_gate` 等)——
   网格密度是精度/速度权衡而非器件设计变量,混入会让 LLM 误判。
   `device.structure`/`polarity`/`external`/`n_fins`/
   `n_stacked_sheets`/`simulation.type` 等结构/拓扑字段同样排除
   (会破坏 `check_sim_structure` 或需要重新分网语义)。

## 架构设计

### 1. 新模块布局

```
src/cfet_tcad/optimize/            # 新包,纯 Python 核心不依赖 PySide6/anthropic
    __init__.py
    schema.py          # FIELD_BOUNDS(手工维护的可调参数边界表,
                        #   与 gui/config_form.py 现有 CHOICES 字典同一惯例)
    objective.py        # ObjectiveTerm/ObjectiveSpec/extract_metric/score
    llm_provider.py      # LLMProvider ABC、CandidateProposal、
                          # LLMProviderError、FakeProvider(测试用)
    prompt.py           # build_round_prompt()、RESPONSE_JSON_SCHEMA
    orchestrator.py      # Orchestrator(QObject)——轮次循环主控
    llm_worker.py        # LLMWorker(QObject)——QThread 里跑阻塞 API 调用
    claude_provider.py   # ClaudeProvider(LLMProvider)——懒加载 anthropic

src/cfet_tcad/gui/
    optimize_dialog.py   # OptimizeSetupDialog(模态,配目标/候选数/轮数)
                          # OptimizeMonitorDialog(非模态,进度+结果表)
                          # OptimizeExperimentModel(ExperimentModel 子类)
```

`orchestrator.py`/`llm_worker.py` 依赖 PySide6 与
`gui.run_queue.RunQueue`/`gui.experiment_table.ExperimentModel`,因此
虽在 `optimize/` 包下但需要 `[gui]` extra;`claude_provider.py` 是
唯一 import `anthropic` 的文件,且在 `__init__` 内懒加载,不装
`[llm]` 也能正常 import 其余部分。

**复用点(具体到函数)**:
- `orchestrator.py` 直接调用 `workflow.config.apply_overrides` /
  `build_config` / `check_sim_structure` / `resolve_external_mesh`
  做进程内预校验(见"验证时机");
- 每轮候选原样调用 `RunQueue.make_experiment()` / `.add()` /
  `.run_all()` 物化配置并启动——这个函数已经做好了
  `apply_overrides` + `resolve_external_mesh` + `Changes` 列 diff;
- `objective.py`/prompt 历史表统一走
  `workflow.sweep.flatten_fom()` 拍平 FOM,并复用 `sweep.py` 里
  "优先最大 |Vd|/nFET 分支"的取值 fallback 逻辑(适配 idvg 多曲线、
  CFET 嵌套 FOM 的取值歧义),而不是重新发明;
- "Adopt best" 直接复用 `gui.params_dialog.ParamsDialog`
  (`save_as_dir=configs_dir`),与 `MainWindow.edit_experiment()`
  现有 Save-As 路径完全一致。

### 2. 执行引擎:用 RunQueue,不用 sweep.py 的 Pool

选 `RunQueue` 而非 `sweep.py` 的 `multiprocessing.Pool`:
- 监控窗口要求"实时看到每个候选的状态",`RunQueue` 天然提供
  (`experiment_changed`、`ExperimentModel` 状态着色、
  `Experiment.overrides`/`.changes` 本身就是"Δ参数"数据);
  `sweep.py` 的 `Pool.map` 是同步阻塞、整批跑完才有结果。
- 每轮给 `Orchestrator` 一个**独立的 RunQueue 实例**(不是
  `MainWindow.queue`),`idle` 信号即"本轮完成";`stop()` 时调用
  已加固过的 `RunQueue.shutdown()`(kill+wait),不影响主表里用户
  手动排的其他实验,也不共用 `max_parallel`。
- 代价:N 次 QProcess 启动开销,相对于每个候选动辄秒级到分钟级的
  真实求解可忽略。

### 3. LLM 调用线程模型

`QThread` host 一个 `LLMWorker(QObject)`,**必须通过信号槽跨线程
调用**(`moveToThread` 后 `Orchestrator` 发一个 `Signal` 请求,自动
走 QueuedConnection;`LLMWorker` 用 `proposal_ready`/`proposal_failed`
信号把结果送回 GUI 线程),不能直接调用 worker 方法(那样仍在调用者
线程执行,起不到线程隔离作用)。已知限制:`QThread.wait()` 无法
强制打断正在进行的 HTTP 请求;用短 client 超时缓解,并在
`Orchestrator`/`LLMWorker` 里维护 `_stopping` 标志,丢弃 stop 之后
才到达的迟到响应。

### 4. Prompt / 参数边界设计

`FIELD_BOUNDS` 手工维护(现有 dataclass 校验是命令式 `if` 语句,没有
声明式元数据可提取;做 AST 解析或重构成声明式校验都是更大范围、
本次不做的重构)。新增
`tests/test_optimize_schema.py` 把边界值跑一遍真实 `build_config`
做漂移防护测试。`FIELD_BOUNDS` 只含前述已确认的可调参数子集。

每轮 prompt 含:目标函数(度量/方向/约束)、可调参数及其边界与当前
值、**完整历史表**(每个历史候选的 overrides、状态
`ok`/`rejected: 原因`/`error: 原因`、完整拍平后的 FOM——不是精简
摘要、以及计算出的标量分数)、当前最优候选、本轮请求的候选数与
JSON 输出 schema。用 Claude 的结构化输出(`json_schema` response
format),非工具调用循环——这是一次性结构化抽取,不是开放式 agentic
探索。数值边界无法用 JSON Schema 强约束(Claude 结构化输出不支持
`minimum`/`maximum`),边界只在 prompt 文字里说明,真正兜底仍是
`build_config()`。

### 5. 验证时机:轮内重试

每个候选先经 `apply_overrides` → `resolve_external_mesh` →
`build_config` → `check_sim_structure` 在 GUI 线程内快速校验(纯
Python,不碰 DEVSIM/gmsh),不合法的候选**不进入 RunQueue**,而是
在同一轮内追加一次"修复"请求(默认预算 2 次),把被拒绝的
overrides+原因喂回去只要求补那几个空位。修复预算耗尽后用剩余合法
候选跑;若某轮修复后一个合法候选都没有,计入独立的"验证失败轮"
计数器(默认上限 3),触顶则终止整个优化并给出清晰报错。

### 6. 安全/成本护栏

- `max_rounds`(默认 8)、`n_candidates`(默认 4,防御性截断超额
  返回)、轮间墙钟预算(默认 60 分钟,只在两轮之间检查,不打断正在
  跑的一轮)。
- LLM API 失败分类处理:网络错误/限流→有限重试+退避;JSON 解析
  失败→一次澄清重问;鉴权失败→不重试,首轮就报清晰错误。
- 与既有加固衔接:`Orchestrator.stop()` 依次 quit+wait LLM 线程、
  调用 `RunQueue.shutdown()`;`MainWindow.closeEvent` 扩展为同时
  确认并停止所有打开的 `OptimizeMonitorDialog`
  (`self._optimize_dialogs` 列表);`OptimizeMonitorDialog` 自身
  `closeEvent` 复刻主窗口"有活动任务先确认再停止"的模式,单独关闭
  监控窗口不会留下后台线程/进程。

### 7. 新依赖

`pyproject.toml` 新增独立的 `[llm]` extra(`anthropic>=0.40`),不
并入 `[gui]`,避免只用手动扫描/仿真的用户被迫装 `anthropic` 及其
传递依赖。API key 走 `ANTHROPIC_API_KEY` 环境变量(SDK 默认解析
方式);设置对话框只显示只读状态行("在环境变量中找到"/"未设置"),
v1 不做密钥输入框或持久化存储——避免过早引入 `keyring` 依赖和平台
差异,后续若要 GUI 内配置可作为独立小版本加。

### 8. 目标函数细化

`constraint: tuple[Literal["<","<=",">",">="], float]`;跨轮维护
每个 metric 的 running min/max 做归一化(不是逐轮归一化,首轮样本
太少无意义);违反约束用与违反幅度成正比的惩罚项而非打成 `-inf`,
保证"矮子里拔将军"仍可比较;`weight` 默认 1.0 均权,v1 的目标构建
UI 只暴露 Metric/Direction/Constraint 三列,不做权重编辑(数据结构
留了扩展空间)。

### 9. GUI 集成点

- `RowActions`(`main_window.py`)新增 `Optimize` 按钮,与现有
  Run/Stop/Edit/Sweep/Structure 同一 `_btn()` 模式;
- `config_menu()` 新增"Optimize..."右键项,直接对浏览到的 YAML
  发起(不需要先 Add 成实验行);
- `MainWindow.open_optimize_dialog(base_config_path)`:先 `.exec()`
  一个同步的 `OptimizeSetupDialog`(配目标/候选数/轮数/provider,
  风格同 `SweepDialog`),确认后创建 `Orchestrator` +
  非模态 `OptimizeMonitorDialog`,`.show()` 并 append 到
  `self._optimize_dialogs`;
- 监控窗口的结果表是 `ExperimentModel` 子类
  `OptimizeExperimentModel`,只加"最优高亮"和一个"Score"列(存在
  独立的 `dict[Experiment, float]` 里,不污染共享的 `Experiment`
  dataclass),其余列(Experiment/Status/Vt/SS/Ion/Ioff/Changes)
  全部免费复用现有模型;
- "Adopt best" 按钮:`ParamsDialog(best_exp.config_path,
  save_as_dir=configs_dir, save_as_name=f"{stem}_optimized")`,与
  `edit_experiment()` 现有 Save-As 完全同一套逻辑。

### 10. 测试策略

- 纯单测(无 Qt 无网络,新增 `tests/test_optimize_*.py`):
  `objective.py` 打分/归一化/惩罚数学;`schema.py` 边界值回归
  `build_config` 的漂移防护;`prompt.py` 历史表/目标段落生成;
  `llm_provider.py` 的 `FakeProvider`/`LLMProviderError` 契约。
- `@pytest.mark.slow` + `qapp` fixture + 假 CLI(复刻
  `tests/test_gui.py` 里 `monkeypatch.setattr(rq, "cli_command",
  lambda: (sys.executable, ["-c", script]))` 的手法,不碰真实
  DEVSIM):`Orchestrator` + 真 `RunQueue` + `FakeProvider` 跑
  2 轮×2 候选,断言轮次推进(靠 `idle`)、历史累积、最优追踪、
  `max_rounds` 生效、无进程/线程泄漏;`FakeProvider` 先给一个越界
  候选再修复,断言越界候选从未进 `RunQueue`;监控对话框中途关闭
  触发 `orchestrator.stop()` 且无孤儿进程。
- 一条 `@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"))`
  的真实 `ClaudeProvider` 冒烟测试,本地手动跑,CI 不强制。

### 11. 交付顺序(4 个可独立评审的提交)

1. 纯 Python 基础(`schema.py`/`objective.py`/`llm_provider.py`
   含 `FakeProvider`/`prompt.py` + 各自单测)——无 Qt 无网络,风险
   最低,可独立评审;
2. `orchestrator.py` + `llm_worker.py`,接真 `RunQueue`,用
   `FakeProvider` 做端到端 `qapp` 测试——线程正确性/轮次推进这个
   最高风险点在碰 GUI 对话框之前先跑通、测好;
3. GUI 对话框(`optimize_dialog.py`)+ 新入口(RowActions/右键菜单)
   + `closeEvent` 扩展 + Adopt 走 `ParamsDialog`——仍用
   `FakeProvider`,不接真实 LLM;
4. `claude_provider.py` + `[llm]` extra + provider 选择器接线 +
   可选门控冒烟测试——最小、最独立的一块,插进已经跑通的框架里。

## 关键文件

- `src/cfet_tcad/optimize/orchestrator.py`、`objective.py`、
  `llm_provider.py`、`schema.py`、`prompt.py`、`llm_worker.py`、
  `claude_provider.py`(全部新建)
- `src/cfet_tcad/gui/optimize_dialog.py`(新建)
- `src/cfet_tcad/gui/run_queue.py`(只读复用,大概率不改动内部逻辑)
- `src/cfet_tcad/workflow/config.py`(只读复用 `apply_overrides`/
  `build_config`/`check_sim_structure`/`resolve_external_mesh`)
- `src/cfet_tcad/workflow/sweep.py`(只读复用 `flatten_fom` 与
  FOM 取值 fallback 逻辑)
- `src/cfet_tcad/gui/main_window.py`(新增 RowActions 按钮、右键菜单
  项、`open_optimize_dialog`、`closeEvent` 扩展)
- `src/cfet_tcad/gui/params_dialog.py`(只读复用 Save-As 机制)
- `pyproject.toml`(新增 `[llm]` extra)
- `tests/test_optimize_*.py`(新建)

## 待实现前需要人工过一遍的判断

- `FIELD_BOUNDS` 的具体字段清单(几何/掺杂/功函数/迁移率标定因子
  的完整枚举与上下界数值)需要一次人工审阅,Plan agent 只给出了
  代表性样例;
- `ClaudeProvider` 默认模型:建议 `claude-sonnet-5`(而非 Opus)——
  多轮多候选的结构化抽取任务,成本延迟优先于开放式推理能力,模型
  id 仍做成可配置字段。

## 验证

1. 四个交付阶段各自跑 `pytest`(新增用例逐步变绿,现有 136 个不
   回归);
2. 阶段 2 完成后:`FakeProvider` 端到端测试断言无孤儿 QProcess/
   QThread(参考现有 `test_close_event_stops_running_jobs` 的检查
   手法);
3. 阶段 3 完成后:xvfb 截图核对 Optimize 按钮/右键项/监控窗口
   非模态行为/结果表实时更新/Adopt 走通 Save-As;
4. 阶段 4 完成后:本地手动设置 `ANTHROPIC_API_KEY` 跑一次真实
   2D nanosheet 器件优化(如 `configs/nsheet_nfet_2d.yaml`,目标
   "maximize ion_ioff_ratio, constrain ss_mv_per_dec < 75"),确认
   全链路(prompt→候选→校验→并行仿真→FOM 回填→下一轮)可用;
5. 按 CLAUDE.md 惯例:完成后归档 `docs/dev_plan_llm_optimizer.md` +
   追加 `docs/DEV_PLANS_ARCHIVE.md` + 刷新 `docs/PROJECT_DEV_PLAN.md`;
   推送后提醒用户此功能改动了 `[llm]`/`[gui]` extras,需要手动重新
   触发 Windows 打包工作流才能让 Windows exe 里出现该功能(或明确
   排除在 Windows 包之外,这也是需要在实现时再确认的一点)。


## 结果

四阶段全部落地,与计划设计基本一致,实施中修正/细化了三处:

1. **`FIELD_BOUNDS` 从"仅 prompt 上下文"改为真正硬约束**:实测发现
   `build_config` 的校验大多只是 `> 0`,一个 999nm 的栅长会被判定
   "合法"通过。`Orchestrator._validate_candidate` 因此显式对每个
   override 值做 `FIELD_BOUNDS` min/max 区间检查,再走
   `build_config`/`check_sim_structure` 兜底,`schema.py` 的文档
   同步改口说明这一点。
2. **修复轮内修复(repair)丢失被拒候选历史的 bug**:第一次校验失败的
   候选如果通过后续修复请求补上,原候选从未被记入 `history`——加了
   `_round_invalid` 累积列表,轮次结束时统一写入。
3. **修复跨轮打分不可比较的 bug**:归一化分数在"发现新高点"那一刻
   总是自归一化为 1.0,导致后一轮真正更优的候选反而因为严格 `>`
   比较不过前一轮的旧最优。改为每轮结束后对全部历史 `done` 记录用
   当前 tracker 范围统一重新打分(`O(轮数×候选数)`,可忽略的开销)。

`OptimizeExperimentModel` 的 Score 列与 Experiment 的关联没有直接把
`Experiment` 塞进纯 Python 的 `RoundRecord`(会破坏 `optimize.*` 不依赖
PySide6 的目标),而是给 `RoundRecord` 加 `eq=False`(身份语义可哈希)
后在 `Orchestrator` 上单独维护 `_exp_by_record`/`exp_scores` 两个
旁路字典。

Windows 打包:选择**纳入**而非排除——`[llm]` 已加进两条 workflow 的
安装行,与 `[gui]`/`[viz]` 一样默认打包;`anthropic` 是纯 Python +
httpx 依赖链,预期能被 PyInstaller/Nuitka 的标准导入发现机制正确
收集,但未经实机验证,若下次手动触发的 Windows 构建暴露打包问题
（例如 httpx/certifi 数据文件收集不全）,按本项目一贯做法现场诊断
修复即可。

测试 136 → 190(新增 54 个,全部离线:`FakeProvider`/假 CLI 子进程/
注入 `sys.modules["anthropic"]` 的假 SDK,不需要网络或真实 API key),
新增文件对应四个阶段:
`tests/test_optimize_{schema,objective,llm_provider,prompt}.py`（阶段1）、
`tests/test_optimize_orchestrator.py`（阶段2）、
`tests/test_optimize_gui_dialog.py`（阶段3）、
`tests/test_optimize_claude_provider.py`（阶段4,含一条真实网络冒烟
测试,`skipif` 门控在 `ANTHROPIC_API_KEY` 上,CI 不强制）。

xvfb 截图核对:行内 Optimize 按钮、YAML 右键 Optimize… 菜单项、
设置对话框(目标编辑器 + 候选数/轮数/provider)、监控对话框(真实
假 CLI 驱动的两轮结果、best-so-far 正确选中更高 l_gate_nm 候选)
均按预期工作,已收录进 User Guide(`optimize_setup.png` /
`optimize_monitor.png`)。

落地于提交:见 git log 中本计划对应的提交(`docs/PROJECT_DEV_PLAN.md`
Phase 11 记录了具体范围)。
