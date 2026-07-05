# cfet_tcad

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

每次运行在 `output.directory` 下产生：

- `idvg.csv` / `idvd.csv` — 全部偏压点的端电流
- `idvg.png` / `idvd.png` — 转移/输出特性曲线
- `fom.json` — 提取的器件参数（Vt 恒流法/最大 gm 法、SS、DIBL、Ion/Ioff）
- `vtk/` — 各偏压点的 `.vtu`（每 region 一个）+ `.visit` / `.vtm` /
  汇总 `.pvd`（timestep = 偏压值），VisIt 直接 `Open` `.visit` 或 `.pvd`
  即可动画播放整条扫描曲线上的电位/载流子分布

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
- `cfet_3d`（Phase 3）：完整 3D CFET —— 两个 3D 环栅纳米片垂直堆叠，
  每片带环绕氧化壳与独立功函数的环栅接触（gate_n/gate_p 共栅）。复用
  gaa_3d 的结构化块网格引擎与 cfet_2d 的命名/极性映射模式；cfet_idvg
  与 cfet_vtc 实验无需改动直接运行。3D 堆叠内 nFET 指标与单管 3D GAA
  仿真逐位一致。

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
configs/             # nFET/pFET Id-Vg、nFET Id-Vd 示例
examples/            # Python API 示例
tests/               # pytest: 几何/加载/提取/配置/求解冒烟
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
- 运行测试：`pytest`（约 15 秒，含两个粗网格平衡态求解冒烟测试）。
