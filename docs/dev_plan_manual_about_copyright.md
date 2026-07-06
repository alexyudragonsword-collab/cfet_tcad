# Help 增加中英对照《软件说明书》+ About 增加版权信息

## Context

用户要一份**中英文双语软件说明书**放进 Help,至少含:软件特性、
适用范围、对标主流软件结果、局限;并在 About 里加版权信息。

现状(已核对):
- Help 是单窗口 `HelpView`(`gui/help_view.py`),渲染
  `help/guide.html`(EN)/`guide_zh.html`(ZH),顶部语言开关切换——
  这是**操作型用户指南**(安装/上手/结构/物理/实验/命令行/排错);
- About(`gui/about_dialog.py` 的 `ABOUT_HTML`)有版本/作者/组件/
  "License: Apache-2.0",但**无版权行**;仓库**无 LICENSE 文件**
  (About 与 pyproject 都声称 Apache-2.0,却缺文件);
- `src/cfet_tcad/__init__.py` 有 `__version__/__author__/__app_name__`,
  无 `__copyright__`;
- 基准数据现成:`docs/paper_comparison.md`(对标 Jiang et al./AMAT
  论文的 Sentaurus 级 TCAD,四项 Ion 方向全部一致);
- 打包:`help/` 下 html 由 `collect_data_files`(PyInstaller)/
  include-package-data(Nuitka)自动带上,新增 manual.html 无需改
  打包脚本。

说明书用**中英文语言开关**(和现有 User Guide 一样,不同时呈现两种
语言):英文 `manual.html` + 中文 `manual_zh.html` 两份单语文件,顶部
下拉切换。作为 Help 菜单里 User Guide 之外的新条目,不动现有两份指南。

## 改动

### 1. 双语说明书(新 `manual.html` + `manual_zh.html`)

`src/cfet_tcad/gui/help/` 下**两份单语文件**(英文 manual.html、中文
manual_zh.html),内容对应、由语言开关切换;沿用 guide.html 的
h1/h2/表格样式,纯文字无图(免资产管理)。每份含章节:

(每份文件为单语——英文版全英文、中文版全中文,下同)

1. **软件简介 / Overview** —— 一句话定位:基于 Python + DEVSIM +
   gmsh 的开源 CFET/堆叠纳米片器件级 TCAD,桌面工作台对标 Synopsys
   Sentaurus;版本 0.5,作者 Yu Rui。
2. **软件特性 / Features** —— 结构(nanosheet_2d/gaa_3d/cfet_2d/
   cfet_3d/external + STEP 导入 + 多沟道复制)、物理(DD、
   Caughey-Thomas/CVT-Lombardi 迁移率、速度饱和、密度梯度量子修正、
   SiGe(x)、面取向迁移率标定)、实验(idvg/idvd/cfet_idvg/
   混合模式 VTC)、提取(Vt 恒流&max-gm、SS、DIBL、Ion/Ioff、噪声
   容限)、工作流(SWB 式实验表、并行 DOE、CSV 设计点、每行操作按钮、
   进度%、3D VTK、STL/OBJ/STEP 导入导出)、跨平台(Linux +
   Windows 独立 exe,Windows MKL PARDISO / Linux OpenBLAS+UMFPACK)、
   开源 Apache-2.0。
3. **适用范围 / Scope** —— 面向先进 CMOS(GAA 纳米片、CFET、堆叠
   器件,3nm 及以下)的教学/研究级器件仿真、方法学开发、DOE;
   明确**不适用**:量产工艺/版图签核、专有格式互操作、应力/环振
   电路签核。
4. **对标主流软件 / Benchmarking** —— 两部分:
   (a) Sentaurus 组件对应表(SDE/SDevice/Mixed-mode/Visual/SWB →
   本系统对应件,复用 guide.html 首表);
   (b) 器件级复现结果(取自 `docs/paper_comparison.md`):对标
   Jiang et al.(AMAT,商用 Sentaurus 级 TCAD)的 FBC vs SBC CFET,
   Ion@Ioff=1nA 四项方向全一致(SBC nMOS +7.7% vs 论文 +10%、
   SBC pMOS −9.1% vs −5%、宽 SBC +48.9%/+28.0% vs +73%/+47%),
   SS 72–76 mV/dec;并提内部位精确交叉验证(不连通 region 块对角
   求解、2×并联电流 rel<1e-6)。
5. **局限 / Limitations** —— 取 `paper_comparison.md` 差异来源 +
   `PROJECT_DEV_PLAN` 能力边界:无版图(GDSII/OASIS)导入、无
   Sentaurus 专有格式(TDR/BND/CMD)、无应力迁移率模型(靠
   mobility_scale 手动标定)、无寄生 RC/环振瞬态(电路级止于
   反相器 VTC 混合求解)、3D fin 用旋转 GAA 近似、量子修正 3D 默认
   关闭、迁移率取向比取文献值而非逐曲线 BTE 标定。
6. **版权与许可 / Copyright & License** —— `Copyright © 2026
   Yu Rui`,Apache-2.0;与 About 一致。

### 2. 说明书查看器(`src/cfet_tcad/gui/help_view.py`)

复用现有 HelpView 的语言开关机制(不新写带 toggle 的类):

- 把 `HelpView.__init__` 泛化为 `HelpView(guides=GUIDES,
  title="User Guide / 用户指南", parent=None)`——默认参数保持现有
  行为(现有 `HelpView()` 调用与测试不变);
- 新增 `MANUALS = {"English": "manual.html", "中文": "manual_zh.html"}`
  与 `manual_path(language)`;
- 说明书即 `HelpView(guides=MANUALS, title="Manual / 说明书")` 的
  一个实例,自带同款中英语言开关(默认跟随系统 locale)。

### 3. Help 菜单 + 窗口(`src/cfet_tcad/gui/main_window.py`)

- `self.manual = HelpView(guides=MANUALS, title="Manual / 说明书")`,
  作为独立窗口(图标/标题/尺寸,仿 `self.help`);
- Help 菜单在 User Guide 与 About 之间插入
  **"Manual (中英双语) / 说明书"** → `show_manual()`(show+raise+
  activate,仿 `show_help`);
- `closeEvent` 里一并 `self.manual.close()`(跟随主窗口)。

### 4. About 版权(`about_dialog.py` + `__init__.py`)

- `__init__.py` 增 `__copyright__ = "Copyright © 2026 Yu Rui"`;
- `ABOUT_HTML` 增版权行(用 `cfet_tcad.__copyright__`)并把
  "License: Apache-2.0" 明确为 "Licensed under the Apache License,
  Version 2.0";保留 Yu Rui / 0.5(现有测试依赖)。

### 5. LICENSE 文件(新 `LICENSE`)

补 Apache-2.0 全文(About 与 pyproject 已声称却缺文件),版权持有人
Yu Rui、2026。修正现有不一致。

### 6. 测试(`tests/test_gui.py`)

- 更新 `test_main_window_constructs`:Help 动作列表加 Manual 条目;
  `show_manual()` 后 manual 窗口可见、随主窗口关闭;
- 更新 `test_about_dialog_and_version`:断言 `__copyright__` 存在且
  版权行(含 "2026"/"Yu Rui")进入 ABOUT_HTML;保留原断言;
- 新增 `test_manual_renders_with_toggle`:`manual_path("English")` 与
  `manual_path("中文")` 均存在;`HelpView(guides=MANUALS)` 有语言
  开关,切到 English 文本含 "Features"/"Scope"/"Limitations"/"Ion",
  切到中文含 "软件特性"/"适用范围"/"局限"(验证单语切换、不并列)。

### 7. 文档 / 归档

- 按 CLAUDE.md:`docs/dev_plan_manual_about_copyright.md` +
  DEV_PLANS_ARCHIVE.md 追加 + PROJECT_DEV_PLAN 索引/状态刷新;
- 推送后提醒:Windows 打包待手动触发(manual.html 随 help/ 打包)。

## 验证

1. 全套 pytest 绿(新增 ~1、改 2);
2. xvfb 截图:Manual 窗口(英文与中文各一张,展示语言开关)+
   About(版权行),发用户过目;
3. 打包侧无改动(数据收集已覆盖 help/*.html)。

## 风险

- 基准数字须与 `docs/paper_comparison.md` 逐字一致 → 直接抄表;
- About 现有测试断言 "Yu Rui"/"0.5" → 保留;
- Manual 窗口生命周期仿 help 窗口(随主窗口关闭)→ 有既有模式与
  单测覆盖;
- QTextBrowser 对中文/UTF-8 → 复用 guide 已验证的 UTF-8 载入 helper。

## 结果

按计划落地(见本次提交):Help 菜单新增「Manual (中英双语) / 说明书」,
打开独立窗口,复用 HelpView 的中英语言开关(泛化 `HelpView(docs,
title)`,默认参数保持旧行为),渲染新增的 `manual.html` /
`manual_zh.html`——单语切换、不并列,含软件简介/特性/适用范围/
对标主流软件(Sentaurus 对应表 + AMAT 论文四项 Ion 复现)/局限/
版权六节。About 增版权行(`__copyright__ = "Copyright © 2026
Yu Rui"` + Apache-2.0 明示 + 免责声明);补 `LICENSE` 全文
(修正此前 About/pyproject 声称却缺文件的不一致)。测试 112 → 113。
