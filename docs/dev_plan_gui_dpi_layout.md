# GUI 分辨率自适应 + 左面板可自由伸缩

## Context

用户反馈两个问题:(1) GUI 不随屏幕分辨率自适应,1920×1280 下**面板
比例错乱**(已确认症状);(2) 左侧 YAML 文件面板无法自由伸缩,**被
folder 路径卡住**。

根因(已核对源码,两个问题同源):

- `folder_label` 是普通 QLabel,其 sizeHint/minimumSizeHint = 完整
  路径文本宽度。路径一长(Windows 下常见几百像素):
  ① hsplit 初始分配按 size hint → 左面板被撑得很宽,右侧工作区被
  挤压 → "比例错乱";② QLabel 最小宽度即文本宽度 → 分割条拖不小
  → "被卡住"。
- 固定像素几何按 1280×800 标定:`resize(1280, 800)`、
  `center_split.setSizes([220, 440])`(`main_window.py:144,190`)——
  换分辨率后初始比例失真。
- 弹窗 `params_dialog.py:31`(560×720)、`step_dialog.py:68`(720×640)
  固定尺寸,小屏上可能超高。
- **Structure 3D 面板同病**(用户补充):`structure_view.py:94` 的
  `self.title.setText(str(vtk_dir))` 把完整结果目录路径塞进标题
  QLabel,文本宽度撑宽整个 Structure 3D 面板。

## 改动

### 1. ElidedLabel(新公共小模块 `src/cfet_tcad/gui/widgets.py`)

新增 `ElidedLabel(QLabel)`,主窗口 folder 路径与 StructureView 标题
两处共用:

- `minimumSizeHint()` 返回很小的宽度(如 40px,高度沿用父类)——
  彻底解除对左面板收窄的钳制;
- `paintEvent` 用 `fontMetrics().elidedText(text, Qt.ElideMiddle,
  width)` 绘制(路径中段省略:`C:\Users\…\configs`);
- `sizeHint()` 宽度同样收敛(如 160px),不再按全文撑面板;
- `setText` 重载同步刷 tooltip = 全文(StructureView 的调用点就不用
  各自补 tooltip);main_window 的 folder_label 与
  `structure_view.py` 的 `self.title` 都换成 ElidedLabel
  (StructureView 里 title 还承担错误信息显示,省略号行为同样适用)。

### 2. 分辨率自适应的窗口与分割条初始几何

- `__init__` 里 `resize(1280, 800)` 改为按主屏可用区域取 ~85% 并
  居中:`QGuiApplication.primaryScreen().availableGeometry()`
  (screen 为 None 时回退 1280×800,offscreen 测试环境安全);
- 删除固定 `center_split.setSizes([220, 440])`;改为**首次
  showEvent** 时按真实尺寸做比例分配(一次性 flag):
  - `hsplit.setSizes([w*0.16, w*0.84])`(左侧文件面板 ~1/6);
  - `vsplit.setSizes([h*0.78, h*0.22])`(日志 ~1/5);
  - `center_split.setSizes([ch/3, 2ch/3])`(实验表 1/3,维持既有
    约定);
  此后用户拖动/窗口缩放交给既有 stretch factor,行为不变;
- hsplit/vsplit/center_split 需提为 `self.hsplit`/`self.vsplit`
  (showEvent 与测试要用)。

### 3. 弹窗尺寸钳制

`ParamsDialog`/`StepConvertDialog` 的固定 `resize(w, h)` 改为对屏幕
可用区域取 min(公用小函数 `fit_to_screen(w, h)` 同放
`gui/widgets.py`):`resize(min(w, aw*0.9), min(h, ah*0.9))`。

### 4. 测试(tests/test_gui.py)

- `folder_label` 与 `StructureView.title` 都是 ElidedLabel 且
  `minimumSizeHint().width() < 80`(超长路径下也不钳制所在面板);
  设一个超长路径的 project_root / load_dir 验证;
- 首次 show 后:`center_split.sizes()` 比例 ≈ 1:2(容差 ±15%),
  `hsplit.sizes()[0]` 占总宽 ≤ 25%——offscreen 平台有虚拟 screen,
  可直接 `win.show()` + `qapp.processEvents()` 断言;
- 窗口尺寸不超过 `primaryScreen().availableGeometry()`。

### 5. 验证与交付

- 全套 pytest 绿;
- xvfb 分别以 `-screen 0 1920x1280x24` 与 `-screen 0 1366x768x24`
  起 GUI 截图(带演示行 + 长路径),核对两种分辨率下比例一致、
  左面板可拖窄(截图发用户);
- 按 CLAUDE.md 归档(dev_plan_gui_dpi_layout.md + 两总档 + 索引);
- 推送后提醒:需再手动触发 Windows 打包(可与 STEP 导入一起拿)。

## 风险

- offscreen 测试环境的虚拟屏幕尺寸与真实屏不同 → 断言只做比例/上限,
  不做绝对像素;
- showEvent 一次性初始化与用户随后拖动互不干扰(flag 保护);
- ElidedLabel 换掉的是显示,populate_configs 的 setText/setToolTip
  调用点不变。

## 结果

按计划落地(见本次提交):新公共模块 `gui/widgets.py`
(`ElidedLabel` 中段省略 + tooltip 全文 + 最小宽度 40px;
`fit_to_screen` 弹窗钳制),folder 路径 label 与 StructureView 标题
两处换用;主窗口尺寸改为主屏可用区域 85% 并居中,分割条改为首次
showEvent 按真实尺寸比例分配(hsplit 16%、vsplit 78%、center 1/3、
bottom 对半),之后交还 stretch factor。xvfb 以 1920×1280 与
1366×768 双分辨率截图核对:比例一致、路径省略、左面板可拖窄。
测试 108 → 110,全绿。
