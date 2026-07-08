# STACKED CMOS TCAD

（Python 包 / CLI 名：`cfet_tcad` / `cfet-tcad`）

开源 CFET / 堆叠纳米片器件 TCAD 仿真系统，基于 **Python + DEVSIM + gmsh**，
输出 VTK 供 **VisIt / ParaView** 可视化。对标 Synopsys Sentaurus 工具链。

An open-source CFET / stacked-nanosheet device TCAD simulation system built
on Python, DEVSIM (drift-diffusion solver), and gmsh (parametric meshing),
with VTK output for VisIt/ParaView — benchmarked conceptually against the
Synopsys Sentaurus tool chain.

## 与 Sentaurus 的组件映射

| Sentaurus 组件 | 本系统模块 | 说明 |
|---|---|---|
| Structure Editor (SDE) | `cfet_tcad.geometry` | gmsh Python API 参数化几何 + 结构化网格 |
| Sentaurus Device (SDevice) | `cfet_tcad.physics` + `cfet_tcad.solve` | DEVSIM 漂移扩散求解 |
| Sentaurus Visual | `cfet_tcad.io` → VisIt | VTK (.vtu/.pvd/.visit) + matplotlib |
| Workbench (SWB) | `cfet_tcad.workflow` | YAML 配置驱动 + CLI |
| Inspect | `cfet_tcad.extract` | Vt / SS / DIBL / Ion/Ioff 提取 |

## 安装

```bash
pip install -e .          # 安装 devsim、gmsh、numpy、scipy、matplotlib、pyyaml
pip install -e '.[dev]'   # 附加 pytest
```

系统依赖：DEVSIM 运行时需要 BLAS/LAPACK（如 Debian/Ubuntu 的
`libopenblas0`），gmsh 需要 `libglu1-mesa`。包会在导入时自动定位
版本化的 OpenBLAS 并设置 `DEVSIM_MATH_LIBS`。

## 快速开始

```bash
# nFET 纳米片 (CFET 上层管): 2D Id-Vg 双 Vd 扫描 + 参数提取 + VTK
cfet-tcad run configs/nsheet_nfet_2d.yaml

# pFET 纳米片 (CFET 下层管)
cfet-tcad run configs/nsheet_pfet_2d.yaml

# 输出特性 Id-Vd
cfet-tcad run configs/nsheet_nfet_idvd_2d.yaml

# 完整 3D 环栅 (GAA) 单纳米片 Id-Vg (约数分钟)
cfet-tcad run configs/gaa_nfet_3d.yaml

# density-gradient 量子修正版 nFET (对比经典版观察 Vt 偏移/体反型)
cfet-tcad run configs/nsheet_nfet_2d_dg.yaml

# "全物理" nFET: Lombardi CVT + density-gradient 同开 (Sentaurus 默认组合)
cfet-tcad run configs/nsheet_nfet_2d_full.yaml

# 完整 CFET 堆叠: nFET-on-pFET 共栅, 单次耦合求解同时输出 n/p 转移特性
cfet-tcad run configs/cfet_2d.yaml

# CFET 输出特性 (cfet_idvd): 每个固定共栅偏压下同时扫出 n/p 两管 Id-Vd
cfet-tcad run configs/cfet_idvd_2d.yaml

# CFET 反相器 VTC: 器件/电路混合求解 (对标 Sentaurus mixed-mode)
cfet-tcad run configs/cfet_vtc_2d.yaml

# 完整 3D CFET: 两个堆叠的 3D 环栅纳米片, 共栅联合求解 (约数分钟)
cfet-tcad run configs/cfet_3d.yaml

# SiGe 沟道 pFET 的 CFET (异质材料 + 功函数重调, 提升 n/p 驱动平衡)
cfet-tcad run configs/cfet_2d_sige.yaml

# 只生成网格
cfet-tcad mesh configs/nsheet_nfet_2d.yaml

# 参数扫描 (对标 Sentaurus Workbench DOE): 栅长缩放研究, 4 进程并行
cfet-tcad sweep configs/nsheet_nfet_2d.yaml \
    -p device.l_gate_nm=10.5,12,15,18,21 -j 4 -o results/lg_scaling

# 成组参数 DOE (--zip): Ge 组分扫描 + 每组分同步重调栅金属保持等 Vt
cfet-tcad sweep configs/cfet_2d_sige.yaml --zip -j 4 \
    -p device.channel_material_p=Silicon,SiGe15,SiGe30,SiGe45 \
    -p device.gate_workfunction_p_ev=4.72,4.655,4.59,4.525
```

Python API 等价用法见 `examples/run_idvg.py`、`examples/run_idvd.py`。

## 设计导入与导出

**外部网格导入**（`structure: external`）：直接仿真用户自备的 gmsh
MSH 2.2 ASCII 网格（其他版本用 `gmsh in.msh -save_all -format msh2 -o
out.msh` 转换），配置里给出物理组到 region/contact/interface 的映射与
掺杂方式（`lateral_sd` 解析剖面 / `uniform` 均匀 / `expression` 任意
DEVSIM 表达式），坐标单位为 cm：

```yaml
device:
  structure: external
  external:
    mesh_file: my_device.msh        # 相对配置文件所在目录
    dimension: 2
    regions: {bulk: Silicon, gox: Oxide}
    contacts: {source: bulk, drain: bulk, gate: gox}
    interfaces: {si_ox: [bulk, gox]}
    doping:
      bulk: {profile: uniform, donors_cm3: 1.0e17, acceptors_cm3: 0}
```

**STEP（CAD）导入**：任意 CAD 软件导出的 `.step`/`.stp` 装配体可直接
转成可仿真网格。写一份 import spec（把每个 solid 映射到
region/材料,按包围盒标注 contact 面与掺杂）后一条命令完成转换,输出
`.msh` + 一份可直接运行的 starter 配置（`structure: external`,按接触
命名自动推断单管/CFET 仿真类型）：

```bash
cfet-tcad import-step configs/paper_fbc_cfet_demo_import.yaml \
    -o configs/paper_fbc_cfet_demo.msh
cfet-tcad run configs/paper_fbc_cfet_demo_run.yaml
```

仓库自带两个论文级 CFET 演示件：`configs/paper_fbc_cfet_demo.step`
（forksheet/FBC）与 `configs/paper_sbc_cfet_demo.step`（双片 SBC），
均配好 import spec 与运行配置;GUI 里在左侧 CAD 分区右键 →
"Convert to mesh…" 即可完成同样流程（`examples/make_paper_*_step.py`
是这两个 STEP 的生成脚本）。

**CSV 设计点导入**：DOE 表格（Excel 导出即可）直接驱动 sweep,列名为
点分配置路径,每行一次仿真;导出的 `sweep_summary.csv` 改一改可直接
回灌（状态/FOM 列自动忽略）。GUI 的 Sweep 对话框有同款 "Import CSV"：

```bash
cfet-tcad sweep configs/nsheet_nfet_2d.yaml --points doe.csv -j 4
```

**几何导出**：`structure` 命令可把器件几何导出为 STL/PLY/VTP（表面网
格,任何环境可用）或带材质颜色的 OBJ+MTL（需要 GL,同 `--png`）;GUI 的
Structure 3D 标签页有对应 "Export..." 按钮：

```bash
cfet-tcad structure configs/cfet_3d.yaml --stl device.stl --obj device.obj
```

仿真结果本身始终同时落盘 CSV（I-V）、`fom.json`（参数提取）、VTK
（VisIt/ParaView）与 gmsh `.msh`。

## 图形界面（对标 Sentaurus Workbench）

```bash
pip install -e '.[gui]'    # 安装 PySide6-Essentials
cfet-tcad-gui              # 在项目根目录启动（读取 ./configs 与 ./results）
```

单窗口布局（三个可拖拽分区 + 左侧文件面板），交互范式对标 SWB：

- **左侧文件面板**：上下两个分区分别列出配置文件夹（菜单栏 Open 可
  切换，路径显示在列表上方）里的设计（`.yaml`）与 CAD 模型
  （`.step`）。YAML 双击/右键 Edit 弹出参数编辑器，右键还有
  Add（注册为实验行）/Copy/Delete；STEP 右键 "Convert to mesh…"
  转网格、"List volumes" 列出实体。
- **Experiments 实验表**（上方，SWB 实验表格）：每行一个实验点，行内
  按钮 Run / Stop / Edit / Sweep / Structure 直接驱动该行；状态色块随
  运行流转（浅灰=待运行 / 灰=排队 / 黄=运行中(带百分比) / 绿=完成 /
  红=失败 / 灰蓝=已停止），完成后 Vt/SS/Ion/Ioff/DIBL 列自动回填,
  最右 Changes 列显示该行配置相对原始设计的改动;双击行加载其结果；
  工具栏 Run All / Stop All 全局启停。运行失败会弹出带错误尾部的
  对话框（细节同时在日志面板）。
- **参数编辑弹窗**（Edit 按钮 / 双击 YAML）：从配置 dataclass 自动
  生成的分组表单，下拉框覆盖结构/迁移率/量子模型/材料等枚举项，
  保存前经完整配置校验；Save 覆盖原文件,Save As 可存回 configs/
  变成新设计。
- **Results 分区**（左下,Sentaurus Visual/Inspect）：matplotlib 交互
  画布重绘 CSV 曲线（log/linear 切换、缩放/平移工具栏）+ 展平的
  FOM 表,五种实验类型（含 cfet_idvd 输出特性）都有对应画法。
- **Structure 3D 分区**（右下,SDE + Sentaurus Visual 3D）：
  PyVista/VTK 交互三维渲染（需 `pip install -e '.[viz]'`）——行内
  Structure 按钮对该行配置做"只建结构不求解"的快照预览
  （`cfet-tcad structure`,掺杂着色），双击已完成实验行则加载其偏压
  快照，字段下拉切换 Structure/NetDoping/Potential/Electrons/
  Lambda_n，可剖切、可选偏压点、可导出 STL/OBJ；无 pyvista 时优雅
  降级为提示。命令行等价：
  `cfet-tcad structure configs/cfet_3d.yaml -o out --png device.png`。
- **Sweep… 对话框**（行内 Sweep 按钮）：多行 `path=v1,v2,...` 参数
  网格（可选 zip 成组、可 Import CSV），在表格中展开为逐点任务，
  限并发并行执行,每个点的 Changes 列相对原始设计。
- 每个实验在独立 OS 进程中运行（QProcess 驱动 CLI，与 DEVSIM 全局
  状态要求一致），关窗前会确认并停止在跑任务；日志面板默认过滤
  求解器迭代噪声（可开 verbose）。帮助菜单内置双语 User Guide 与
  软件说明书（中/英切换）。

无显示器环境（CI/容器）可用 `QT_QPA_PLATFORM=offscreen` 运行与测试。

### Windows 独立版（免装 Python）

两条独立的 GitHub Actions 构建跑道（均为**手动触发**：Actions 页选中
工作流点 "Run workflow"，或推 `v*` 标签做发布构建；工件在 Actions
运行页下载，打 tag 时附到 Release），包内都含
DEVSIM+MKL、gmsh、Qt、VTK 全部运行时，Windows 11 x64 免装 Python：

- **Windows EXE**（PyInstaller）→ 工件 `cfet-tcad-windows-x64`：
  onedir 双可执行 —— `cfet-tcad-gui.exe`（工作台）+ `cfet-tcad.exe`
  （命令行，GUI 的每个仿真子进程也调用它）。
- **Windows EXE (Nuitka)** → 工件 `cfet-tcad-windows-x64-nuitka`：
  Nuitka 把 Python 编译为 C 后的单一 `cfet-tcad.exe` 分发器 ——
  无参数启动 GUI，带参数即命令行（`--windows-console-mode=attach`：
  终端里有输出、双击不弹黑框）；启动更快，首次构建耗时更长
  （CI 有编译缓存）。

解压后 exe 旁边的 `configs/` 目录内含全部示例设计（2D/3D 纳米片、
CFET 堆叠、SiGe、量子修正等），GUI 双击启动即在左侧列出。

首次运行 SmartScreen 可能提示"未知发布者"（二进制未签名），
选"仍要运行"即可。

每次运行在 `output.directory` 下产生：

- `idvg.csv` / `idvd.csv` — 全部偏压点的端电流
- `idvg.png` / `idvd.png` — 转移/输出特性曲线
- `fom.json` — 提取的器件参数（Vt 恒流法/最大 gm 法、SS、DIBL、Ion/Ioff）
- `vtk/` — 各偏压点的 `.vtu`（每 region 一个）+ `.visit` / `.vtm` /
  汇总 `.pvd`（timestep = 偏压值），VisIt 直接 `Open` `.visit` 或 `.pvd`
  即可动画播放整条扫描曲线上的电位/载流子分布

**用 ParaView 查看**：`File → Open` 选 `vtk/cfet_idvg.pvd`（timestep=
偏压值，播放键即动画）→ 着色下拉选字段（`mu_n_cvt` 为 CVT 迁移率，
lombardi 运行才有）→ `Clip` 滤镜剖开器件复现 Fig.8 视角。仓库附
`examples/paraview_macro_fig8.py` 宏（Macros → Import new macro 导入后
一键完成上述步骤）；OSPRay 光追出版级渲染在宏尾注释处开启。本项目
不依赖 ParaView——宏运行在你自己的 ParaView 里，是文档的可执行形态。

参考结果（Lg=15nm、t_si=5nm、EOT=1nm、Vdd=0.7V 双栅纳米片，本仓库默认配置）：
SS ≈ 74 mV/dec，DIBL ≈ 90 mV/V，Ion/Ioff ≈ 1–2×10⁵，nFET/pFET 高度对称。

## 器件与物理模型

**几何**（`device.structure` 选择）：

- `nanosheet_2d`（Phase 1）：2D 沟道纵截面双栅结构 —— GAA 纳米片的标准
  2D 近似。单硅区（源/漏延伸区用解析高斯尾掺杂剖面）+ 上下栅氧 +
  上下金属栅。gmsh transfinite 结构化三角网格，硅体内向界面加密。
- `gaa_3d`（Phase 2）：完整 3D 环栅单纳米片。硅条 t_si × W 截面，栅段
  四面包裹 t_ox 氧化层壳（3×3×3 结构化块网格、transfinite 四面体），
  外壳表面为单一 `gate` 接触。物理组命名契约与 2D 一致，物理/求解/提取
  模块零改动复用；2D 电流按有效宽度换算，3D 电流为真实安培。
- `cfet_2d`（Phase 3）：完整 CFET 堆叠 —— nFET 纳米片叠在 pFET 纳米片
  之上，四个栅接触共栅（n/p 可用不同功函数金属），中间为栅金属间隔
  （接触终结电域，不参与网格）。两片在同一 DEVSIM device 中单一 Newton
  系统联合求解；掺杂极性与 DG 载流子按片自动选择。`cfet_idvg` 实验以
  CMOS 对偏置（nFET 源接地/漏 Vdd，pFET 源 Vdd/漏接地）扫共栅，一次
  扫描同时产出 n/p 两条转移曲线与双份参数提取。堆叠中每管指标与单管
  仿真逐位一致（栅金属屏蔽下的交叉验证）。
- `cfet_3d`（Phase 3）：完整 3D CFET —— nFET 器件叠在 pFET 器件上，
  每个沟道带环绕氧化壳与独立功函数的环栅接触（gate_n/gate_p 共栅）。
  **每器件支持多沟道几何复制**：`n_fins`/`fin_pitch_nm` 横向并排
  （fin 阵列，如论文的 2-fin FBC），`n_stacked_sheets`/`sheet_pitch_nm`
  纵向叠层（多纳米片堆叠，如 2-sheet SBC）——复制体并入同一
  region/接触物理组，加载器/物理/求解/渲染零改动，双沟道电流与
  2×单沟道逐位一致（并联精确性测试守护）。与 `n_sheets`（纯电流乘数，
  不产生网格）正交。复用 gaa_3d 的结构化块网格引擎与 cfet_2d 的
  命名/极性映射模式；cfet_idvg 与 cfet_vtc 实验无需改动直接运行。

**参数扫描 / DOE**（`cfet-tcad sweep`，对标 Sentaurus Workbench）：
任意配置参数的点分格（多个 `-p` 取笛卡尔积），每点在独立 OS 进程中跑
完整流水线（DEVSIM 全局状态要求进程隔离，`maxtasksperchild=1`），
`-j N` 并行。输出每点子目录 + 扁平化 `sweep_summary.csv/json`；一维数值
扫描的 Id-Vg 实验自动生成 SS/DIBL/Vt/Ion-Ioff 趋势图。参考结果：默认
nFET 的 Lg 缩放（10.5→21nm）复现经典短沟道退化 —— Lg=21nm 时
SS=64/DIBL=34，Lg=15nm 时 74/90，Lg≤12nm 因 t_si=5nm 的自然长度极限
电学失效（Ioff 超过恒流判据）。

**混合器件/电路仿真**（`cfet_vtc` 实验，对标 Sentaurus mixed-mode）：
反相器输出 Vout 为浮空电路节点（`circuit_element` 大电阻到地创建节点，
两管漏接触经 `contact_equation(circuit_node=...)` 把电流注入该节点的
KCL），器件场量与 Vout 在同一 Newton 系统自洽求解。默认 CFET 堆叠的
VTC：满摆幅、VM=0.338V（与 cfet_idvg 电流交越点一致）、NML/NMH ≈
0.30/0.32V、短路电流钟形峰 ~1.7µA。

两者均输出 MSH 2.2 ASCII（DEVSIM 唯一支持的 gmsh 格式）。

**输运**：Poisson + 电子/空穴连续性（Scharfetter-Gummel 离散化）、
SRH 复合、迁移率三档可选（`const` / `doping` / `doping_vsat`）：
Caughey-Thomas 掺杂依赖低场迁移率 + Caughey-Thomas 速度饱和。
迁移率表达式内联进 SG 电流公式，利用 DEVSIM 的模型感知符号求导
（`diff()`）获得含场依赖项的精确 Newton 雅可比。

**异质沟道材料**：Ge 组分为连续设计变量 —— 材料名 `SiGeNN`（NN =
Ge 百分比 0-50）动态解析到 `sige(x)` 插值工厂（Eg、n_i、介电、电子/
空穴迁移率对组分线性插值，锚定 sige(0)=Silicon、sige(0.30)=SiGe30；
vsat/CVT/DG 参数保持 Si 值作标定旋钮）。按半导体区独立选材：单管
`device.channel_material`，CFET 堆叠 `channel_material_n/_p`（两片被
栅金属电学隔离，无异质结耦合，各区参考能级自洽）；栅功函数的 midgap
参考自动取所栅控片的材料。组分研究（等 Vt，`--zip` 成组重调栅金属）：
n/p 驱动平衡随 x 单调升 0.65 (Si) → 0.72 (x=0.15) → 0.76 (0.30) →
0.81 (0.45)，代价是 Ioff 随禁带变窄上升（209→456 pA）。

**垂直场迁移率退化**（`mobility_model: lombardi_vsat`，2D 与 3D）：
Lombardi (CVT) 表面声子 + 表面粗糙度散射，Matthiessen 与掺杂低场迁移率
及速度饱和合成。垂直场 E⊥ 需要矢量场，用 DEVSIM element 级装配：
`element_from_edge_model` 重构场分量（3D 含 z 分量），SG 电流改建为
element 模型接入连续性/接触方程（element 与 edge 电流在同迁移率下逐位
一致，作为装配正确性测试固化在 test_lombardi 中）；维度感知的导数生成
（三角形 @en0-2 / 四面体 @en0-3）。经典求解收敛后经 `cvt_scale` 同伦升
到全强度。CVT 指纹在 2D 与 3D 上一致：线性区 Ion −24~28%（迁移率主导）、
饱和区 −11~12%（速度饱和掩盖）、SS/DIBL 不变。注意 element 表达式必须
用 `@en*` 访问器书写（`@n0` 与 `@en0` 取值相同但求导独立，详见
physics/lombardi.py 模块注释）。

**全物理组合**：CVT 与 density-gradient 可同开（量子载流子的 element
电流 Bernoulli 驱动势换为有效势 ψ∓Λ，CVT 迁移率保持静电场驱动）。
装配顺序：经典 DD → CVT 同伦 → DG 方程 + element 电流量子化 → DG 同伦。
四模型对照（同一 15nm nFET，线性区）：经典 Ion 11.6µA / CVT 8.3 / DG
10.0 / 全物理 6.4µA —— 各单项效应在组合中保持原量级（Vt 偏移全部来自
DG +18mV，Ion 退化近似乘性叠加），无病态串扰；2D/3D 均收敛。

**量子修正**（`physics.quantum_model: density_gradient`，默认关闭）：
Bohm 量子势 density-gradient 模型，输运载流子增加一个量子势解变量
Λ（nFET 修正电子、pFET 修正空穴，全耦合 Newton）：

- `n = n_i·exp((ψ−Λ_n−φ_n)/V_t)`，DG 方程用对称化通量形式装配；
- **各向异性**：量子势只作用于限域方向（y/z），输运方向（x）权重为 0
  —— 与 Sentaurus 各向异性 eQuantumPotential 同一实践，避免虚假的
  源漏势垒平滑推高 Ioff/SS；
- Si/SiO2 界面用氧化层势垒 Robin 边界条件
  `∂√n/∂n̂ = −√n/d_pen`（d_pen≈0.16nm），产生体反型/界面载流子排斥；
- 收敛用 dg_scale 同伦阶梯（0→1，失败自适应二分）；
- 强度可通过 `physics.dg_gamma_n/p` 标定。

默认器件（t_si=5nm）上 DG 相对经典解：Vt +15~17mV、Ion −15%、
Ioff −38%、SS/DIBL 基本不变，界面电子密度压低 ~60×、反型峰移到片中心
（体反型）—— 方向与量级符合 DG 物理。已知局限：未在氧化层内求解 DG
（穿透用 Robin BC 近似）。

**求解**：非线性 Poisson（电中性初值）→ 提升为耦合 DD →（可选 DG 同伦）
→ 自适应偏压斜坡（失败步长减半）。默认开启 128 位扩展精度求解选项。

## 目录结构

```
src/cfet_tcad/
├── geometry/        # 参数化几何: params.py (DeviceParams/MeshParams/命名契约)
│   │                #   base.py (GeometryBuilder 抽象基类 + MeshLayout)
│   └── nanosheet_2d.py
├── meshio_devsim/   # gmsh .msh → DEVSIM device
├── physics/         # materials.py / doping.py / mobility.py / equations.py
├── solve/           # initial.py (平衡态) / sweep.py (偏压斜坡与测量)
├── extract/         # figures_of_merit.py
├── io/              # vtk_export.py / results.py
└── workflow/        # config.py / runner.py / cli.py
configs/             # 20+ 示例设计: 2D/3D 纳米片、CFET 堆叠(转移/输出/VTC)、
                     #   SiGe、量子修正、论文复现、STEP 演示件(.step + import spec)
examples/            # Python API 示例、STEP 生成脚本、ParaView 宏
tests/               # pytest: 几何/加载/提取/配置/求解/GUI/STEP 导入/3D 渲染
```

## 路线图

- **Phase 1**：2D 双栅纳米片截面全流程 ✔
- **Phase 2**：3D 单纳米片 GAA ✔；density-gradient 量子修正 ✔
- **Phase 3**：完整 CFET 堆叠（nFET-on-pFET 共栅联合求解）✔；
  CFET 反相器 VTC（器件/电路混合求解）✔；3D CFET 堆叠 ✔
- 参数扫描 / DOE（多进程并行，`cfet-tcad sweep`）✔
- Lombardi (CVT) 垂直场迁移率（element 级装配，2D + 3D）✔
- 异质沟道材料（SiGe30 pFET，按区材料架构）✔
- element 级量子电流（CVT + DG 全物理组合）✔
- Ge 组分连续插值 + 成组参数 DOE（--zip）✔
- **有意不做的项**：多纳米片网格化 —— 在本系统的接触终结栅模型下与
  `n_sheets` 电流缩放严格等价（CFET 堆叠的逐位交叉验证已证明栅金属
  完全屏蔽片间耦合），网格化只增加计算量不增加物理；要使其有意义需
  合并 S/D 外延（片间寄生耦合），列为将来的结构扩展。氧化层内 DG ——
  Robin 穿透边界已捕获主效应，残余精度差异由 `dg_gamma` 标定吸收。

## 开发注意事项

- DEVSIM 表达式解析器中一元负号优先级高于 `^`：`-a^2 == (+a)^2`，
  指数必须整体加括号（见 `physics/doping.py`）。
- `devsim.reset_devsim()` 会清掉 UMFPACK direct solver 注册，
  使用 `cfet_tcad.reset()` 代替（tests/conftest.py 依赖此行为）。
- 运行测试：`pytest -m "not slow"` 数十秒完成快速子集；全量 `pytest`
  （140 个上下，含 2D/3D 全流程与 STEP 导入的慢速用例）约数分钟，
  Linux CI 对每次 push 跑全量。
