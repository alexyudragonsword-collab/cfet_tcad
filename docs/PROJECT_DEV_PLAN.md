# STACKED CMOS TCAD — 工程完整开发计划与状态

> 本文档是项目的持续性记录，**定期更新**（每完成一个阶段性功能后同步）。
> 与 `docs/dev_plan_*.md` 系列（单次功能/plan-mode 计划的存档）不同，
> 本文件是唯一的、面向全工程生命周期的主计划——只写里程碑摘要，不重复
> 存档文件里的实施细节。

最后更新：提交 `6b05d4e` 构建收尾（分支 `claude/cfet-tcad-simulation-zh2kfo`）。

## 0. Plan-mode 计划归档索引

每次 `/plan` 模式生成并经批准执行的详细代码计划，完成后都归档
（计划原文 + Context/改动/验证，末尾补一段"结果"）。

**全量归档：`docs/DEV_PLANS_ARCHIVE.md`** —— 本项目全部 **13 份**
plan-mode 计划的完整原文（从会话 transcript 逐字恢复，含上下文压缩前
的早期计划），按时间排序，每份附执行结果与对应提交：

| # | 计划 | 对应提交 |
|---|---|---|
| 1 | CFET TCAD 仿真系统 — 实施计划（Phase 1-3 蓝图） | `e50b8ee` 起 |
| 2 | Density-Gradient 量子修正 | `0dd234c` |
| 3 | CFET 反相器 VTC（电路节点耦合） | `3878ff5` |
| 4 | Lombardi 垂直场迁移率退化（element 级） | `51f043a`/`0813011` |
| 5 | element 级量子电流（CVT×DG 全物理） | `5a8f6ae` |
| 6 | SiGe(x) 组分插值 + 成组参数 DOE | `32b46b5` |
| 7 | PySide6 桌面 UI | `5297edb` |
| 8 | 3D 器件结构渲染 | `05a4938` |
| 9 | GitHub Actions 构建 Windows 11 独立 exe | `2b57285`→`163dfdc` |
| 10 | 设计导入/导出（外部网格 + CSV + STL/OBJ） | `e26dec9` |
| 11 | configs/ 示例设计打进 Windows exe 包 | `cee0109` |
| 12 | doctor Windows 临时目录清理修复 | `60b1816` |
| 13 | 论文复现：FBC/SBC CFET 对比 | `0e41666`→`0aa300e` |
| 14 | cfet_3d 多沟道复制（多 fin/多 sheet）+ meshwell/ParaView 评估 | `21076d9` |
| 15 | GUI 进度百分比 + 单实验停止/删除 | 本次提交 |

其中 11 起均有独立文件（`dev_plan_windows_exe_configs_bundling.md`、
`dev_plan_windows_exe_doctor_tempfile_fix.md`、
`dev_plan_paper_cfet_comparison.md`、`dev_plan_multi_channel_cfet.md`、
`dev_plan_gui_progress_stop_delete.md`，为本约定建立后的逐份归档）。
今后新计划继续逐份归档为 `dev_plan_<slug>.md` 并同步加入
DEV_PLANS_ARCHIVE.md 与本索引。

（GUI 截图/图标/改名/Help 合并、Windows 现场故障三连修、Fig4/8/9
可视化等改动是直接执行的实现或修复，未经过 `/plan` 模式，故不在本
索引，均记录于下方阶段回顾。）

## 1. 项目定位

开源 CFET（互补场效应晶体管，nFET/pFET 垂直堆叠纳米片）TCAD 仿真系统，
Python + DEVSIM（漂移扩散求解器）+ gmsh（参数化网格）+ VTK/VisIt（可视化），
对标 Synopsys Sentaurus 工具链五大组件：

| Sentaurus 组件 | 本系统模块 |
|---|---|
| Structure Editor (SDE) | `geometry/`（gmsh 参数化几何 + 结构化网格） |
| Sentaurus Device (SDevice) | `physics/` + `solve/`（DEVSIM 漂移扩散） |
| Sentaurus Visual | `io/`（VTK 输出，PyVista 3D 渲染） |
| Workbench (SWB) | `workflow/`（YAML 配置 + CLI + sweep/DOE 引擎）+ `gui/` |
| Inspect | `extract/`（Vt/SS/DIBL/Ion/Ioff/VTC 参数提取） |

版本 0.5，作者 Yu Rui，程序显示名 **STACKED CMOS TCAD**（Python 包名/CLI
命令仍为 `cfet_tcad`/`cfet-tcad`，标识符不可含空格）。

## 2. 当前状态一览

- **源码**：`src/cfet_tcad/` 约 5200 行（44 个模块文件）
- **测试**：`tests/` **90 个测试**，含 5+ 组位精确交叉验证
- **示例配置**：`configs/` 16 个 YAML（2D/3D 纳米片、CFET 堆叠、SiGe、
  量子修正、VTC、论文复现 5 个：Ion/Ioff 对比 3 个 + Lombardi 迁移率
  可视化 2 个）
- **提交数**：40（主分支 `claude/cfet-tcad-simulation-zh2kfo`）
- **CI**：Linux 全套 pytest 自动跑（每次 push）；Windows 打包（PyInstaller
  + Nuitka 两条独立跑道）**手动触发**（`workflow_dispatch` 或 `v*` 标签）
- **GUI**：PySide6 桌面工作台，5 大功能区（Experiments/Parameters/
  Results/Structure 3D + Help 菜单），应用图标已配

## 3. 开发阶段回顾（按提交顺序的里程碑）

### Phase 1 — 2D 双栅纳米片基础（`e50b8ee`）
标准 DD 物理 + Caughey-Thomas 迁移率 + 高斯尾掺杂剖面；gmsh built-in
内核结构化三角网格；nFET/pFET Id-Vg/Id-Vd 全流程跑通。

### Phase 2 — 3D 化 + 量子修正
- `c0dc6fe` 3D GAA 单纳米片（`_BlockGrid` 结构化块网格引擎，物理组命名
  契约复用 2D 版本，物理/求解/提取模块零改动）
- `0dd234c` density-gradient 量子修正（Bohm 势，Robin 氧化物界面项，
  √(n+1) 正则化，仅对多子求解稳定）

### Phase 3 — 完整 CFET 堆叠
- `3406553`/`7a8b1cc` 2D/3D CFET 堆叠（nFET 叠 pFET，共栅耦合求解）
- `3878ff5` 反相器 VTC（`circuit_element` + `contact_equation(circuit_node=)`
  混合器件/电路自洽求解，对标 Sentaurus mixed-mode）
- `930952c` sweep/DOE 引擎（每点独立 OS 进程，DEVSIM 全局状态隔离）

### Phase 4 — 高级物理
- `51f043a`/`0813011` Lombardi CVT 表面迁移率（2D→3D，element-based
  E⊥ 重建，各向异性权重）
- `d74346d` SiGe 异质材料沟道（应变 pFET）
- `5a8f6ae` element 级量子电流（CVT + density-gradient 组合，`@en*`
  独立符号求导的关键坑）
- `32b46b5` 连续 SiGe 组分插值 + zip 成组 DOE

### Phase 5 — GUI 与可视化
- `5297edb` PySide6 桌面 GUI（Sentaurus Workbench 布局）
- `05a4938` 3D 器件渲染（PyVista/VTK，Structure 3D 标签页）
- `7cce79d`/`309a66f` 中英文图文用户指南（QTextBrowser，Help 标签）
- `5fe5e61` About 对话框，版本号 0.5

### Phase 6 — 发布与打包（`fd42f72` → `099c282`）
- Linux CI（GitHub Actions，全套 pytest）
- **两条独立 Windows exe 打包跑道**：
  - PyInstaller（onedir，`cfet-tcad-gui.exe` + `cfet-tcad.exe`）
  - Nuitka（单一分发器 exe，编译为原生代码，启动更快）
- 打包过程中修复的关键坑（均已加回归测试/冒烟）：
  - Windows 下 DEVSIM 的 BLAS（MKL）DLL 定位与加载
  - 非 ASCII 安装路径下 DLL 全路径加载失败（改用 `ctypes.WinDLL`
    预加载 + 裸文件名传给 `DEVSIM_MATH_LIBS`）
  - `libiomp5md.dll`（MKL 线程运行时）漏打包，首次 BLAS 调用才触发
  - 无控制台窗口进程（双击启动的 GUI exe）`sys.stdout/stderr` 为
    `None`，DEVSIM 导入期打印崩溃 → 加 `_ensure_std_streams()`
  - 示例 `configs/` 目录未随包分发
  - cp1252 默认编码读中文用户指南崩溃
  - `cfet-tcad.exe doctor` 自诊断命令（环境报告 + 分步验证 BLAS→
    devsim→gmsh→微型求解）

### Phase 7 — 产品化收尾（`2a5e72d` → `2cb3059`）
- Help 菜单合并至左上角（单一入口）
- 程序改名 **STACKED CMOS TCAD**
- 应用图标（CFET 剖面主题，Qt 窗口 + 任务栏 + 两个 exe 资源图标）
- **设计导入/导出**（`e26dec9`）：
  - 外部 gmsh 网格导入（`structure: external`，物理组映射 + 掺杂
    三种方式：lateral_sd/uniform/expression）
  - CSV 设计点批量导入 sweep（列名=点分配置路径，可与
    `sweep_summary.csv` 导出互通）
  - STL/PLY/VTP/OBJ 几何导出（CLI `--stl/--obj` + GUI Export 按钮）

### Phase 8 — 论文复现（`0e41666` → `7880e2b`，完成）
复现 Applied Materials 论文《Complementary FET Device and Circuit Level
Evaluation Using Fin-Based and Sheet-Based Configurations Targeting 3nm
Node and Beyond》的器件级对比（详见
`docs/dev_plan_paper_cfet_comparison.md`）：

- 新增 `physics.mobility_scale_n/p` 标定旋钮（面取向/应力/BTE 校准的
  低场迁移率乘数，1.0 时表达式字符级不变，不影响既有位精确交叉验证）
- 三个论文尺寸配置：`configs/paper_{fbc,sbc,sbc31}_cfet_3d.yaml`
  （Lg 15nm、gate pitch 45nm、N-P 间距 30nm、sheet 18×5nm、fin 近似
  为旋转 GAA 5×18nm，2 片/器件，Vdd 0.7V）
- `examples/paper_cfet_comparison.py`：恒 Ioff=1nA 提取 Ion，核对论文的
  SBC nMOS +10%/pMOS −5%（同有效宽度）、宽 sheet +73%/+47%（同占地
  面积）趋势——本仿真得到 +7.7%/−9.1%、+48.9%/+28.0%，四项方向全部
  一致，幅度差异在 `docs/paper_comparison.md` 里逐条解释（面取向迁移
  率取文献值而非 BTE 标定、fin 用旋转 GAA 近似、无应力模型）
- **Fig 4/8/9 风格图**（`docs/dev_plan_windows_exe_*`同批未涉及，属于
  同一论文复现主题的延伸，非独立 plan-mode 计划）：`io/render3d.py`
  新增 `sample_line()` + mobility 字段导出（`mu_*_lf_node` 点数据、
  `mu_*_cvt` DEVSIM 自带的单元数据，均无需自建投影代码）；
  `configs/paper_{fbc,sbc}_lombardi_cfet_3d.yaml` + 
  `examples/paper_structure_mobility_figures.py` 产出结构剖面/3D
  迁移率场/一维迁移率剖面三张图（`docs/paper_fig4_structure.png` 等，
  局限说明见 `docs/paper_fig489_notes.md`）

## 4. 已知能力边界（明确声明，非缺陷）

- 无版图（GDSII/OASIS）导入——本系统是器件级 TCAD，工艺仿真前
- 无 Sentaurus 私有格式（TDR/BND/CMD）解析
- 无应力迁移率模型（用 `mobility_scale_n/p` 手动标定近似）
- 无寄生 RC 提取 + 环振瞬态仿真（电路级能力止于反相器 VTC 混合求解）
- 3D fin 用旋转 GAA 近似（四面环栅，非真实三栅+衬底）

## 5. 环境与协作约定（本文档同时记录，避免遗忘）

- 开发分支：`claude/cfet-tcad-simulation-zh2kfo`；`main` 曾在用户明确
  批准后创建过一次（"都做"指令），日常开发仍在 feature 分支
- **Windows 打包工作流手动触发**：`windows-exe.yml` /
  `windows-nuitka.yml` 只响应 `workflow_dispatch` 或 `v*` 标签，绝不
  随分支 push 自动构建（用户明确要求，2026-07-05 起生效）
- v0.5 tag 存在于本地，远程创建需用户通过 GitHub UI 或本地 clone 操作
  （git 代理拒绝 tag push）
- 提交信息统一带 Co-Authored-By 与 Claude-Session 尾注

## 6. 待办 / 下一步候选

- [x] Windows 打包已在 `6b05d4e` 上重新构建全绿（2026-07-05 23:25 手动
      触发）：`cfet-tcad-windows-x64`（PyInstaller, 474MB）与
      `cfet-tcad-windows-x64-nuitka`（Nuitka, 463MB，含 no_docstrings/
      no_asserts 反向工程加固）——包含全部功能与现场修复
- [ ] （可选）环振瞬态仿真——如果需要真正对标论文电路级结论，需新增
      寄生 RC 提取 + 瞬态求解模块，工作量较大，需用户明确需求后立项
- [ ] （可选）Lombardi CVT 表面散射系数（b_ac/delta_sr）按面取向标定
      ——目前只有低场基线（mobility_scale_n/p）区分 FBC/SBC，CVT 衰减
      曲线本身两者相同；`docs/paper_fig489_notes.md` 有展开说明
- [ ] （可选）Fig9 风格迁移率剖面加密限域方向网格（`ny_si` 从 5 提到
      20+）以获得更平滑的对称衰减形状，当前受限于演示速度取舍

---
*更新记录：本文件由 Claude 在里程碑节点手写维护，不做自动生成。*
