# GUI 重构:单条目操作按钮 + 单窗口布局 + YAML 文件管理

## Context

用户对 GUI 工作流提出 6 项调整,核心思想是从「工具栏驱动当前选中配置」
转为「实验条目自治」:每个实验行自带 Run/Stop/Sweep/Structure 按钮,
YAML 文件通过双击/右键直接管理(编辑/加入实验/复制/删除),
Experiments/Results/Structure 合并为一个可调尺寸的复合窗口,取消
Parameters tab。已确认的交互决策:

- 单条目操作 = **每行内嵌小按钮**(表格新增 Actions 列);
- Sweep 生成的扫描点也进入**待仿真(pending)**状态,不自动开跑;
- 已结束条目再点 Run = **原地重跑**(同一输出目录,旧结果覆盖)。

## 现状关键点(已核对源码)

- `gui/main_window.py`:QTabWidget 四个 tab;工具栏 Run/Sweep.../Stop/
  Structure/Open config folder...;Run 从左侧选中 yaml + form 状态出发。
- `gui/run_queue.py`:`enqueue()` 即刻 `_maybe_start()`;调度器只认
  `status == "queued"`;`_procs` 已按 Experiment 身份键控(删行安全)。
- `gui/experiment_table.py`:`COLUMNS` 8 列;`Experiment` dataclass
  (eq=False,可哈希);`STATUS_COLORS` 5 态。
- `gui/config_form.py`:`ConfigForm.load/to_raw/save` 完整可复用,
  直接嵌进弹出对话框,无需改动。

## 改动

### 1. 实验生命周期:新增 pending 态(`gui/run_queue.py` + `experiment_table.py`)

- `Experiment.status` 默认改 `"pending"`;`STATUS_COLORS` 增
  `"pending": QColor("#e8eaed")`(比 queued 更浅的灰);
- RunQueue 拆开「入表」与「开跑」:
  - `add(exp)`:只 `model.add`,不调度(替代原 enqueue 语义);
  - `start(exp)`:pending/stopped/failed/done → 重置
    `progress=None, fom={}`、置 `"queued"`、`_maybe_start()`
    (原地重跑:同 out_dir,CLI 覆盖旧结果);running/queued 时 no-op;
  - `run_all()`:对所有 pending/stopped/failed 条目逐个 `start`
    (done 不自动重跑,避免 Run All 意外覆盖已有结果);
  - `stop(exp)`/`stop_all()` 保持,pending 不受 stop 影响(本来就没跑)。

### 2. Actions 列:每行内嵌按钮(`experiment_table.py` + `main_window.py`)

- `COLUMNS` 在 `"Status"` 后插入 `"Actions"`(`data()` 对该列返回 None);
- `MainWindow` 维护每行一个按钮条(QWidget + QHBoxLayout,4 个紧凑
  QToolButton:**Run / Stop / Sweep / Structure**),通过
  `table.setIndexWidget()` 安装;
- 按钮 lambda 捕获 **exp 对象**(不是行号);
- 行结构变化(`model.rowsInserted/rowsRemoved/modelReset`)→
  `_rebuild_action_widgets()` 全量重装(index widget 不随行移动,
  行数规模小,全量重建最稳);`queue.experiment_changed` → 刷新该行
  按钮使能态:
  - Run:pending/done/failed/stopped 可用;
  - Stop:queued/running 可用;
  - Sweep/Structure:恒可用(以该条目 config 为基);
- `table.verticalHeader().setDefaultSectionSize()` 提高到按钮可容纳的
  行高;Actions 列 `resizeColumnToContents`。

### 3. 工具栏:Run All / Stop All(`main_window.py`)

- 原 Run/Sweep.../Stop/Structure/Open config folder... 全部移出工具栏;
- 新工具栏只剩 **Run All**(`queue.run_all`)与 **Stop All**
  (`queue.stop_all`);
- 删除 `run_current()`(其"从 form 取状态"的路径随 Parameters tab 消失)。

### 4. Open 菜单项 + 文件夹路径显示(`main_window.py`)

- 菜单栏在 Help **左侧**加 `Open` 动作:
  `menuBar().addAction("Open", self.pick_folder)` 先于
  `addMenu(help_menu)` 注册;
- 左侧配置面板改为容器:顶部 `QLabel`(`self.folder_label`)显示当前
  文件夹完整路径 + 下方 `config_list`;`populate_configs()` 同步刷新
  label 文本(setToolTip 同值)。

### 5. Parameters 弹窗(新 `gui/params_dialog.py`)

- `ParamsDialog(QDialog)`:内嵌复用 `ConfigForm`,构造时 `form.load(path)`;
- 按钮:**Save**(覆盖原文件,`form.save(path)`,ValueError 弹警告)、
  **Save As...**(`QFileDialog.getSaveFileName`,默认目录 = 当前 config
  folder,后缀 .yaml)、**Close**;
- 保存成功后发 `saved = Signal(Path)`,MainWindow 接收后
  `populate_configs()` 刷新列表(另存进当前文件夹时新文件立即可见);
- 双击 `config_list` 条目 → 打开该 yaml 的 ParamsDialog(modal exec);
- 移除 QTabWidget 里的 Parameters tab 与 `self.form`(主窗口不再持有
  常驻 ConfigForm)。

### 6. YAML 右键菜单(`main_window.py`)

`config_list.setContextMenuPolicy(Qt.CustomContextMenu)`,菜单四项:

- **Edit** —— 同双击,打开 ParamsDialog;
- **Add** —— `add_config_to_experiments(path)`:
  `queue.make_experiment(stem, path, self._new_out_dir(stem))` →
  `queue.add(exp)`,**pending 态入表,不开跑**;
- **Copy...** —— `QInputDialog.getText` 预填 `<stem>_copy.yaml`,
  确认(即"save")后复制到当前文件夹;目标已存在 → 警告并中止;
  成功后刷新列表;
- **Delete** —— `QMessageBox.question` 确认后 `unlink()`,刷新列表。

文件操作落在可独立测试的方法:`add_config_to_experiments(path)`、
`copy_config(path, new_name)`、`delete_config(path)`(对话框壳保持薄)。

### 7. 单窗口复合布局(`main_window.py`)

- 删除 QTabWidget,中央区改为:

```
QSplitter(Vertical)  self.center_split
├── 上:Experiments 表(约 1/3 高,stretch 1)
└── 下:QSplitter(Horizontal)  self.bottom_split  (stretch 2)
    ├── 左:ResultsView
    └── 右:StructureView
```

- 外层结构保留:hsplit(左配置面板 | center_split)+ vsplit(上述 |
  底部 LogConsole),所有分割条可拖动调整尺寸;
- 双击实验行仍加载 Results + Structure(面板常驻,无需切 tab);
- 单条目 **Structure** 按钮:现 `preview_structure()` 参数化为
  `preview_structure(exp)`,以 `exp.config_path` 为输入、输出到
  `exp.out_dir / "structure"`(避免与 run 的 vtk/ 混写),完成后载入
  右下 StructureView;
- 单条目 **Sweep** 按钮:SweepDialog 不变,base 换成 `exp.config_path`,
  生成的点全部 `queue.add()`(pending,按已确认决策不自动开跑);
  `dlg.jobs` 仍设置 `queue.max_parallel`。

### 8. 测试(`tests/test_gui.py`)

更新:
- `test_main_window_constructs`:菜单断言改
  `["Open", "&Help"]`;tabs 断言改为 center_split/bottom_split 结构
  (子部件数、方向);`folder_label` 文本 == 项目 configs 路径;
- `test_run_queue_materializes_point_config`:`status == "pending"`;
- `test_stop_queued_experiment`:改用 `add`+`start` 组织。

新增:
- pending 不被调度:`add` 后 `_maybe_start()` 不启动;`start(exp)` →
  queued;
- `run_all` 只拉起 pending/stopped/failed,不动 done/running;
- 原地重跑:done 条目 `start()` 后 fom/progress 清空、状态 queued;
- `copy_config`/`delete_config`/`add_config_to_experiments` 文件级
  行为(tmp_path);
- ParamsDialog:load→改字段→Save 覆盖原文件;Save As 写新文件且
  `saved` 信号携带新路径;
- Actions 列存在且 `data()` 为空;按钮使能态随实验状态翻转。

### 9. 文档与归档

- 中英用户指南(`gui/help/`)更新:新布局、每行按钮、yaml 右键菜单、
  Open 菜单;
- 按 CLAUDE.md 约定归档:`docs/dev_plan_gui_single_window_rework.md`
  + `DEV_PLANS_ARCHIVE.md` 追加 + `PROJECT_DEV_PLAN.md` 索引/状态刷新;
- 推送后提醒用户:Windows exe 需手动触发两条打包工作流才能拿到新 GUI。

## 验证

1. 全套 pytest(offscreen,不套 xvfb)绿,新增 ~8 测试;
2. xvfb 下起 MainWindow,`QWidget.grab()` 截图核对布局(上 1/3 实验表
   含按钮列、左下 Results、右下 Structure、左侧路径 label、菜单栏
   Open|Help),发给用户确认;
3. Windows exe 实机验证留给用户(打包需手动触发)。

## 风险

- `setIndexWidget` 与行增删的错位 → 全量重建策略 + 增删行单测;
- 双击行为冲突:实验表双击仍是"打开结果",yaml 列表双击是"编辑",
  两处互不影响;
- 删除 Parameters tab 后 Run 不再经过 form 预校验 —— Add 时
  `make_experiment` 本就重新读 yaml 并物化,合法性由 CLI 侧
  `build_config` 把关(报错落日志 + failed 状态),编辑路径则在
  ParamsDialog Save 时校验。

## 结果

全部 6 项调整按计划落地(见本次提交):pending 生命周期
(`add`/`start`/`run_all`)、每行 Run/Stop/Sweep/Structure 内嵌按钮
(Actions 列 + `RowActions` 条,全量重建策略)、工具栏 Run All/Stop
All、菜单栏 Open(Help 左侧)+ 文件夹路径 label、`ParamsDialog` 弹窗
(Save/Save As,取代 Parameters tab)、YAML 右键 Edit/Add/Copy/Delete、
单窗口三区复合布局(center_split 1/3 : 2/3,setSizes 修正 size-hint
挤压)。测试 99 → 103(净增 4:改 3 增 4 并入),全套绿;xvfb 截图
核对通过(菜单/工具栏/路径 label/按钮使能态/三态色块/布局比例)。
