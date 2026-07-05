# STACKED CMOS TCAD — 工程完整开发计划与状态

> 本文档是项目的持续性记录，**定期更新**（每完成一个阶段性功能后同步）。
> 与 `docs/dev_plan_*.md` 系列（单次功能的临时计划存档）不同，本文件是
> 唯一的、面向全工程生命周期的主计划。

最后更新：提交 `2812d2b`（分支 `claude/cfet-tcad-simulation-zh2kfo`）。

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

- **源码**：`src/cfet_tcad/` 约 5400 行（44 个模块文件）
- **测试**：`tests/` 约 1500 行，**87 个测试**，含 5+ 组位精确交叉验证
- **示例配置**：`configs/` 14 个 YAML（2D/3D 纳米片、CFET 堆叠、SiGe、
  量子修正、VTC、论文复现 3 个）
- **提交数**：35（主分支 `claude/cfet-tcad-simulation-zh2kfo`）
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

### Phase 8 — 论文复现（`0e41666`，进行中）
复现 Applied Materials 论文《Complementary FET Device and Circuit Level
Evaluation Using Fin-Based and Sheet-Based Configurations Targeting 3nm
Node and Beyond》的器件级对比：

- 新增 `physics.mobility_scale_n/p` 标定旋钮（面取向/应力/BTE 校准的
  低场迁移率乘数，1.0 时表达式字符级不变，不影响既有位精确交叉验证）
- 三个论文尺寸配置：`configs/paper_{fbc,sbc,sbc31}_cfet_3d.yaml`
  （Lg 15nm、gate pitch 45nm、N-P 间距 30nm、sheet 18×5nm、fin 近似
  为旋转 GAA 5×18nm，2 片/器件，Vdd 0.7V）
- `examples/paper_cfet_comparison.py`：恒 Ioff=1nA 提取 Ion，生成对比图
  + `docs/paper_comparison.md` 报告，核对论文的 SBC nMOS +10%/pMOS
  −5%（同有效宽度）、宽 sheet +73%/+47%（同占地面积）趋势
- **状态**：三个 3D CFET 仿真在后台执行中，报告待生成

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

- [ ] 完成论文复现三组仿真，生成 `docs/paper_comparison.md` 对比报告
- [ ] 视用户反馈决定是否重新手动触发 Windows 打包（当前 exe 落后于
      设计导入导出、图标、改名等多轮更新）
- [ ] （可选）环振瞬态仿真——如果需要真正对标论文电路级结论，需新增
      寄生 RC 提取 + 瞬态求解模块，工作量较大，需用户明确需求后立项

---
*更新记录：本文件由 Claude 在里程碑节点手写维护，不做自动生成。*
