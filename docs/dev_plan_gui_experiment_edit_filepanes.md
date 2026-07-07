# GUI:文件面板分区 + 实验行 Edit/另存 + 相对原始 yaml 的改动列

## Context

三项 GUI 调整:
1. 左侧文件面板把 `.yaml` 与 `.step` **分成上下两个分区**(各带小标题、
   中间可拖动),不再混在一个列表里;
2. 每个实验行加 **Edit** 按钮,运行前可针对该 run 编辑参数,并能
   **Save As 到 `configs/`**(变成可复用设计);
3. 实验表最右侧加一列,显示该实验配置**相对原始 yaml 的改动**。

已确认(用户选择):文件面板用**上下两分区**布局。

现状(已核对):
- `gui/main_window.py`:单个 `self.config_list`(QListWidget)混装
  yaml+step;`RowActions`(main_window 内)每行 Run/Stop/Sweep/
  Structure;`config_menu` 按后缀分 yaml/step 两支;
  `run_sweep` 调 `queue.make_experiment(name, exp.config_path, out,
  overrides)`。
- `gui/experiment_table.py`:`Experiment(name, config_path, out_dir,
  overrides, status, fom, progress)`;`COLUMNS` 9 列,最后 DIBL;
  "Parameters" 列(index 1)已显示 overrides 摘要。
- `gui/run_queue.py`:`make_experiment(name, base_config, out_dir,
  overrides)` 读 base + apply_overrides → 物化 `out_dir/config.yaml`,
  存 `config_path`+`overrides`。
- `gui/params_dialog.py`:`ParamsDialog(path)` 复用 `ConfigForm`,
  Save 覆盖、Save As 到同目录 `<stem>_copy.yaml`。
- 复用:`workflow.config.apply_overrides`(点路径覆盖)。无现成
  flatten/diff,需新增。

## 改动

### 1. 相对原始 yaml 的改动:数据与计算

- `gui/run_queue.py` 新增纯函数
  `config_changes(config_path, base_config) -> str`:各自 yaml 载入 →
  `_flatten`(递归成点路径 `device.l_gate_nm` 等)→ 逐键比较,输出
  紧凑串,如 `l_gate_nm: 15→12; +mobility_scale_n=0.75; -foo`;两者
  相等则空串。
- `Experiment` 增字段 `base_config: Path | None = None` 与
  `changes: str = ""`(`experiment_table.py`)。
- `make_experiment` 签名调整:`make_experiment(name, source_config,
  out_dir, overrides=None, base_config=None)`——`source_config` 即原
  `base_config`(读取+物化用;`resolve_external_mesh` 仍按
  `source_config.parent` 解析);`base_config` 默认取 `source_config`,
  作为"原始 yaml"用于 diff。物化后计算
  `changes = config_changes(cfg, base_config)`,写入 Experiment。
- `experiment_table.py`:`COLUMNS` 末尾加 `"Changes"`;`data()` 对该列
  返回 `exp.changes`;表头 `setStretchLastSection` 自然让它拉伸。
  ("Parameters" 列保留,仍显示 overrides 摘要。)

### 2. 实验行 Edit 按钮 + 编辑/另存(`main_window.py` + `params_dialog.py`)

- `RowActions` 增 `edit_btn`("Edit"),使能条件同 Run
  (pending/done/failed/stopped;queued/running 时禁用),点击
  `window.edit_experiment(exp)`;`refresh()` 同步其使能态。
- `ParamsDialog` 增可选参数 `save_as_dir: Path | None = None`:
  Save As 的默认目录/文件名指向 `save_as_dir/<stem>.yaml`(缺省保持
  原行为)。
- `MainWindow.edit_experiment(exp)`:running/queued 直接返回;
  `ParamsDialog(exp.config_path, parent=self, save_as_dir=config_folder)`;
  连接 `saved`:
  - 若保存目标 == `exp.config_path`(覆盖该 run 配置):重算
    `exp.changes = config_changes(config_path, base_config)` 并
    `model.update_row(row_of(exp))`;
  - 否则(Save As 到 configs):`populate_configs()` 刷新左侧 YAML 列表。
- `run_sweep` 生成子实验时传 `base_config=exp.base_config`,使扫描点的
  Changes 列相对**原始 yaml**(含父级编辑 + 扫描覆盖)。

### 3. 左侧文件面板:YAML / STEP 上下两分区(`main_window.py`)

- 左面板改为:顶部 `folder_label` + 一个 `QSplitter(Vertical)`:
  - 上分区:`QLabel("Designs (.yaml)")` + `self.config_list`(YAML);
  - 下分区:`QLabel("CAD (.step)")` + `self.step_list`(新 QListWidget);
  - `setStretchFactor(0,3)/(1,1)`(YAML 区更大)。
- `populate_configs`:`config_list ← *.yaml`;`step_list ← *.step/*.stp`。
- 布线拆分:
  - `config_list` 双击→`edit_config`;右键→`config_menu`(**仅 yaml**
    分支:Edit/Add/Copy/Delete,移除 step 分支);
  - `step_list` 双击→`open_step_dialog`;右键→新 `step_menu`
    (Convert to mesh… / List volumes)。
- `self.config_list` 名称保留(测试与既有引用不动)。

### 4. 测试(tests/test_gui.py 等)

- 更新 `test_step_files_listed_and_dialog_template`:.step 现进
  `win.step_list`(断言改 step_list);yaml 仍在 config_list。
- 更新 `test_main_window_constructs`:左面板存在 `config_list` 与
  `step_list`;空项目两者均 0。
- 新增:
  - `config_changes`:改栅长 → `"l_gate_nm: 15→..."` 含改动键;无改动
    → 空串(纯函数,读两个临时 yaml)。
  - `make_experiment` 设置 `base_config`/`changes`;带 overrides 时
    Changes 非空,Changes 列 `data()` 返回它。
  - Edit 按钮:RowActions 有 `edit_btn`,pending 可用、running 禁用;
    `edit_experiment` 打开 ParamsDialog(monkeypatch 掉 exec),
    保存到 config_path 后 exp.changes 更新;Save As 到 configs 后
    新文件进 config_list。
  - `ParamsDialog(save_as_dir=...)`:Save As 默认落在该目录。
- 调整受列序影响的断言(新增列在末尾,既有 index 不变,应无碍)。

### 5. 文档与归档

按 CLAUDE.md:`docs/dev_plan_gui_experiment_edit_filepanes.md` +
DEV_PLANS_ARCHIVE.md 追加 + PROJECT_DEV_PLAN 索引/状态刷新;推送后
提醒手动触发 Windows 打包。

## 验证

1. 全套 pytest 绿(新增 ~5、改 2);
2. xvfb 截图核对:左侧上下两分区(YAML/STEP 各带标题)、实验行含
   Edit 按钮、最右 Changes 列显示如 `l_gate_nm: 15→12`;发用户过目;
3. 手动流:Add 一个配置→Edit 改栅长→Changes 列刷新→Save As 到
   configs→新设计出现在 YAML 分区(单测覆盖等价逻辑)。

## 风险

- 列序变化影响测试 → 新列加在末尾,既有 index 不变;仅个别断言需更新;
- ConfigForm 对 external/cfet_3d 的嵌套 `external:` 字段以单行 YAML 片段
  呈现(既有限制),编辑仍可用,不在本次扩展;
- base_config 传播:扫描点相对原始 yaml diff 依赖
  `exp.base_config` 正确回填(Add 时 = 源 yaml,单测覆盖)。

## 结果

三项按计划落地(见本次提交):
1. 左侧文件面板改为上下两分区(`files_split` 垂直分割:Designs
   (.yaml) / CAD (.step),各带标题、可拖动),`config_list` 只装 yaml、
   新增 `step_list` 装 step;右键菜单拆为 `config_menu`(yaml)与
   `step_menu`(step)。
2. 实验行加 Edit 按钮(pending/done/failed/stopped 可用,queued/
   running 禁用),`edit_experiment` 复用 ParamsDialog(新增
   `save_as_dir`/`save_as_name` 参数),Save 覆盖 run 配置后刷新
   Changes 列,Save As 默认落 configs/ 变可复用设计。
3. 实验表最右加 "Changes" 列,显示配置相对原始 yaml 的紧凑 diff
   (`config_changes` + `_flatten` 纯函数);`Experiment` 增
   `base_config`/`changes` 字段;`make_experiment` 拆
   source_config/base_config 并回填 diff;扫描点相对原始 yaml 计算。
测试 114 → 116,全绿;xvfb 截图核对三项均正确。
