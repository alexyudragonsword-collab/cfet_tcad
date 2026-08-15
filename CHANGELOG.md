# 更新日志

本文件记录 STACKED CMOS TCAD 面向使用者的版本变更。格式参考
[Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循
[语义化版本](https://semver.org/lang/zh-CN/)。

> **说明**：本项目早期未打版本标签，`0.1.0` / `0.5` 两节是依据
> `src/cfet_tcad/__init__.py` 的版本号变更与提交历史回溯整理的，
> 日期取自对应提交。开发过程的完整决策记录见
> `docs/PROJECT_DEV_PLAN.md` 与 `docs/DEV_PLANS_ARCHIVE.md`。

## [未发布] — 0.5.2

当前 `__version__`，尚未发布。

### 新增

- **AI 辅助器件参数优化**（可选功能，需 `[llm]` extra）。实验行的
  `Optimize…` 按钮或 YAML 右键菜单可对一个设计发起 LLM 驱动的参数
  搜索：设定优化目标（度量 + 最大化/最小化 + 约束）后，每轮由模型
  批量提出候选参数，经与命令行完全相同的配置校验后并行跑真实仿真，
  完整 FOM 回灌模型驱动下一轮。监控窗口为非模态，可边跑边用主窗口；
  最优结果可一键"Adopt best"另存为新设计。Provider 层是可插拔接口，
  内置 Claude 实现，API key 走 `ANTHROPIC_API_KEY` 环境变量。
- `cfet_idvd` 仿真类型：CFET 输出特性，每个固定共栅偏压下同时扫出
  n/p 两管的 Id-Vd。
- STEP（`.step`）CAD 模型导入：右键 Convert 或 `import-step` 命令，
  内置论文 Fig.4 风格的 FBC / 双 sheet SBC 两套完整示例。
- `cfet_3d` 几何多沟道复制：每器件支持多 fin（并排）与多 sheet（叠层）。
- Help 中新增中英对照《软件说明书》；About 对话框显示版权信息。

### 改进

- **求解中途不收敛不再丢失全部数据**：偏置扫描中断时，已算出的数据点
  会先落盘（部分 CSV + 日志标注中断点）再抛错。
- GUI 单窗口重构：实验表 + Results + Structure 三区复合布局，分割条
  可调；每行内嵌 Run/Stop/Edit/Sweep/Structure/Optimize 按钮；参数
  编辑改为双击弹窗（Save / Save As）；文件面板分区，新增"相对原始
  YAML 的改动"列；布局随分辨率自适应。
- 配置校验大幅补强：零步长、空偏置列表、非法 `icrit_a`、`vtk_stride`、
  仿真类型与器件结构不匹配（如对 CFET 用 `idvg`）、`n_sheets` 与几何
  复制重复计数——这些此前会在深处报晦涩错误或静默给出错误结果，现在
  在建网格之前就带上下文报错。
- 运行失败时弹窗展示输出尾部，不再只有一行日志。
- 关闭主窗口时若有任务在跑会先确认，并干净地停止子进程，不留僵尸。
- 版本号单源化：`pyproject.toml` 动态读取 `cfet_tcad.__version__`。
- **Windows 包体积减小约 209 MB**（解包 1.3 GB → 约 1.1 GB）：去掉
  重复打包的 gmsh DLL，以及 MKL 中运行时不可达的线程层与向量数学库。
  CPU 分派变体全部保留，不影响任何机器上的求解性能。

### 修复

- GUI 中子进程启动失败（如 CLI 缺失）曾导致实验行永久停留在 running
  并泄漏并行槽位，现在会正确标记失败并释放。
- STEP 转换会用坏掉的 `idvg` 配置覆盖示例自带的运行配置。
- 仿真类型与接触名不匹配时报错信息不可读。

## [0.5] — 2026-07-05

首个具备完整图形界面与 Windows 独立分发能力的版本。

### 新增

- PySide6 桌面工作台（对标 Sentaurus Workbench）：实验队列、参数
  编辑、结果查看、3D 结构渲染（PyVista/VTK）。
- 中英双语图文用户指南，内置于 Help，可离线阅读。
- Windows 独立安装包：PyInstaller 与 Nuitka 两条独立构建跑道，
  免装 Python；示例设计文件随包分发。
- Linux CI：每次 push 自动跑全量测试。
- `doctor` 自检命令：诊断 BLAS 加载链与打包产物完整性。
- 设计导入/导出：外部网格、CSV 设计点、STL/OBJ 几何导出。
- 论文复现：AMAT 3nm 节点 FBC vs SBC CFET 对比仿真与配图。
- 迁移率作为可视化/可导出场量。

### 修复

- 冻结后的 Windows exe 在非 ASCII 安装路径（如中文用户名）下启动崩溃。
- 无控制台窗口模式下 exe 因缺少标准流而崩溃。
- Windows cp1252 编码导致的文本读写乱码（全部文本 IO 改为 UTF-8）。
- 无 OpenGL 的主机上 3D 交互器导致的段错误。

## [0.1.0] — 2026-07-05

初始版本：CFET 纳米片 TCAD 仿真系统核心。

### 新增

- 基于 DEVSIM 的漂移-扩散求解与 gmsh 参数化网格。
- 器件结构：2D 双栅纳米片、3D 环栅（GAA）、CFET 2D/3D 堆叠。
- 仿真类型：`idvg` / `idvd` / `cfet_idvg` / `cfet_vtc`（反相器
  混合器件-电路求解）。
- 物理模型：density-gradient 量子修正、Lombardi(CVT) 垂直场迁移率
  退化（element 级装配，2D/3D）、element 级量子电流、应变 SiGe
  异质沟道与连续组分插值。
- 多进程并行参数扫描 / DOE 引擎（对标 Sentaurus Workbench）。
- FOM 提取：Vt、SS、Ion/Ioff 等。
