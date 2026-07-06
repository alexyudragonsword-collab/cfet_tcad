# GUI 实验表:running 进度百分比 + 单实验停止/删除

## Context

用户提出两个 GUI 增强:(1) 黄色 running 状态提供进度百分比;(2) 增加
单个实验的停止与删除功能(现在只有工具栏 Stop 全停)。

**现状与关键约束**(已核对源码):
- 仿真跑在子进程里(`gui/run_queue.py` 每实验一个 QProcess 驱动 CLI),
  GUI 只能从子进程 stdout 获取信息 → 进度必须由 runner **主动打印**
  机器可读行,RunQueue 解析;
- 偏压点总数在配置里是确定的(vg/vd 范围与步长)→ 百分比 = 已测点/总点,
  语义准确且实现廉价;
- `RunQueue._procs` 以**行号**为键、信号 lambda 捕获行号——删除行会使
  行号漂移,这是删除功能的真正难点,必须先把进程表改为以 Experiment
  **对象身份**为键。

## 改动

### 1. runner 发进度(`workflow/runner.py`)

- `Runner.__init__` 增加 `self._done = 0` / `self._total = 0`;
- 新增 `_announce(total)`(打印 `@@PROGRESS 0/<total>`)与 `_tick()`
  (自增并打印 `@@PROGRESS <done>/<total>`),**必须 `flush=True`**
  (子进程 stdout 非 tty 时块缓冲,不 flush 百分比会攒到最后一起到);
- 各实验入口先算总点数再开跑:
  - `run_idvg`: `len(sim.vd) * (n_steps+1)`
  - `run_idvd`: `len(sim.vg) * (n_steps+1)`
  - `run_cfet_idvg` / `run_cfet_vtc`: `n_steps+1`
- `_sweep` 每 measure 一个点调 `self._tick()`;VTC 循环同理;
- CLI 人工运行时这些行无害(还有用);sweep 引擎的 per-point 日志文件
  里也会出现,无碍。

### 2. RunQueue 重构 + 单实验停止(`gui/run_queue.py`)

- `Experiment` 改 `@dataclass(eq=False)`(身份语义,可哈希——原 eq
  比较字段,两次跑同一配置会撞车);
- `_procs` 改为 `dict[Experiment, QProcess]`;信号 lambda 捕获 exp,
  行号一律实时查 `model.row_of(exp)`(新helper,`experiments.index`);
- 解析进度:`parse_progress_line(line) -> (done, total) | None` 纯函数
  (正则 `@@PROGRESS (\d+)/(\d+)`);`_on_output` 命中则更新
  `exp.progress`、`model.update_row`,**吞掉**该行不进日志面板;
- 新 `stop(exp)`:running → 置 `status="stopped"` 后 kill(
  `_on_finished` 里已是 stopped 的不再改写为 failed);queued → 直接置
  stopped(调度器只认 queued);`stop_all` 改为逐个调 `stop`。

### 3. 表格模型(`gui/experiment_table.py`)

- `Experiment` 增 `progress: float | None = None`;
- `STATUS_COLORS` 增 `"stopped": QColor("#aab7c4")`(灰蓝);
- Status 单元格显示:running 且有进度时 → `"running 45%"`;
- 新 `remove(row)`(beginRemoveRows/endRemoveRows)与 `row_of(exp)`。

### 4. 右键菜单(`gui/main_window.py`)

Experiments 表 `setContextMenuPolicy(Qt.CustomContextMenu)`,菜单项:
- **Stop** —— running/queued 时可用,调 `queue.stop(exp)`;
- **Remove from list** —— 非 running 时可用,调 `model.remove(row)`
  (只移除表格行,**不删磁盘结果**,菜单文字明示);
- **Open results folder** —— `QDesktopServices.openUrl`(顺手的小增强)。
工具栏 Stop(全停)保留。

### 5. 测试(tests/test_gui.py + tests/test_solve_smoke.py 增补)

1. `parse_progress_line` 命中/不命中;
2. Status 单元格文本:running+progress=0.45 → "running 45%";
3. `model.remove` 中间行后顺序/计数正确;Experiment 可哈希;
4. `stop` 对 queued 实验 → "stopped" 且不再被调度(`_maybe_start` 后
   仍 stopped);
5. (slow)tiny idvg 经 `run_config` 跑完,capsys 里 `@@PROGRESS` 行数
   == 总点数+1 且末行 done==total。

### 6. 文档与归档

- 中英用户指南 Experiments 小节补一句(进度百分比、右键停止/移除);
- 按 CLAUDE.md 约定归档:`docs/dev_plan_gui_progress_stop_delete.md` +
  DEV_PLANS_ARCHIVE.md 追加 + PROJECT_DEV_PLAN 索引/状态更新。

## 验证

1. 全套 pytest 绿(新增 ~5 测试);
2. 手动:offscreen 起 GUI 逻辑冒烟已由单测覆盖;真实交互验证留给用户
   在 Windows exe 上做(改动后提醒手动触发打包);
3. Linux CI 绿。

## 风险

- 子进程 stdout 缓冲吞百分比 → 已用 flush=True 针对;若 PyInstaller
  Windows 下仍有缓冲差异,`_ensure_std_streams`/`-u` 兜底可加(实测再说);
- 行号漂移类回归 → 全部行号现算 + 以对象为键,配删除中间行的单测。

## 结果

已实现并推送。runner 每测一个偏压点打印 `@@PROGRESS k/n`(flush),
RunQueue 解析后在 Status 单元格显示 "running 45%",进度行不进日志;
进程表改以 Experiment 对象身份为键(`@dataclass(eq=False)`),右键菜单
提供 Stop / Remove from list(保留磁盘文件)/ Open results folder,
新增 "stopped" 状态(灰蓝)。测试 +5(解析/显示/移除/身份/停止调度
+ slow 进度覆盖测试)。

