# /plan 计划完整归档（按时间顺序）

> 本文件汇集本项目**所有**经 plan 模式生成并批准执行的详细代码计划——
> 从会话历史（含上下文压缩前的完整 transcript）中逐字恢复。早期计划
> 共用一个暂存文件、后一份会覆盖前一份，因此此前只有最近三份有独立
> 归档（`dev_plan_*.md`）；本归档补齐了全部 13 份。每份末尾附执行结果
> 与对应提交。今后新计划按 CLAUDE.md 约定继续以独立文件归档并在此
> 与 PROJECT_DEV_PLAN.md 索引。


---

## CFET TCAD 仿真系统 — 实施计划

### Context

从零构建一个开源 CFET（Complementary FET，堆叠纳米片）器件 TCAD 仿真系统，对标 Synopsys Sentaurus 工具链。技术栈：Python 3.11 + DEVSIM 2.10.0（漂移扩散求解器）+ gmsh 4.15.2（参数化几何与网格）+ VisIt（通过 VTK 文件可视化）。仓库当前为空，全新项目。

**已确认的范围决策**（用户选定）：
- **分阶段，2D 先行**：本期实现 2D 沟道纵截面（双栅近似单纳米片），为 Phase 2（3D GAA 单纳米片）和 Phase 3（完整 CFET 堆叠）预留接口
- **标准 DD + 迁移率模型**：Poisson + 电子/空穴连续性方程、SRH 复合、掺杂/垂直场/速度饱和迁移率；density-gradient 量子修正预留接口不实现
- **完整流水线 + 可运行示例**：几何→网格→求解→参数提取→VTK 输出，含 Id-Vg/Id-Vd 示例

**Sentaurus 组件映射**：

| Sentaurus | 本系统 |
|---|---|
| Structure Editor (SDE) | `geometry/`（gmsh Python API 参数化建模） |
| Sentaurus Device (SDevice) | `physics/` + `solve/`（DEVSIM） |
| Sentaurus Visual | `io/` VTK 输出 → VisIt；matplotlib 曲线图 |
| Workbench (SWB) | `workflow/`（YAML 配置驱动 + CLI + 参数扫描） |
| Inspect | `extract/`（Vt/SS/DIBL/Ion/Ioff/gm 提取） |

### 目录结构

```
cfet_tcad/
├── pyproject.toml              # 依赖: devsim, gmsh, numpy, scipy, matplotlib, pyyaml; CLI 入口 cfet-tcad
├── README.md                   # 架构说明、Sentaurus 映射、使用方法、VisIt 查看指南、Phase 2/3 路线图
├── src/cfet_tcad/
│   ├── geometry/
│   │   ├── params.py           # DeviceParams dataclass: Lg, t_si, t_ox, L_sd, 掺杂浓度, 栅功函数等
│   │   └── nanosheet_2d.py     # gmsh 构建 2D 双栅纳米片截面; 输出 MSH 2.2 ASCII
│   ├── meshio_devsim/
│   │   └── loader.py           # .msh → devsim: create_gmsh_mesh/add_gmsh_region/contact/interface
│   ├── physics/
│   │   ├── materials.py        # Si/SiO2/HfO2 参数库 (eps, Eg, ni, Nc/Nv, 迁移率参数)
│   │   ├── doping.py           # 解析掺杂剖面 (阶跃/高斯结) 注册为 devsim node model
│   │   ├── equations.py        # 非线性 Poisson → 耦合 DD (Scharfetter-Gummel edge models), SRH
│   │   ├── mobility.py         # Masetti 掺杂依赖 + 垂直场退化 + Caughey-Thomas 速度饱和
│   │   └── interfaces.py       # Si/SiO2 界面连续性、栅接触 (功函数偏移)
│   ├── solve/
│   │   ├── initial.py          # 平衡态求解: 先 Poisson-only 后耦合 DD
│   │   └── sweep.py            # 自适应偏压斜坡 (不收敛减半步长)、Id-Vg/Id-Vd 扫描驱动
│   ├── extract/
│   │   └── figures_of_merit.py # Vt (最大gm法/恒流法), SS, DIBL, Ion/Ioff, gm
│   ├── io/
│   │   ├── vtk_export.py       # devsim write_devices(format="vtk") → .vtu 供 VisIt
│   │   └── results.py          # IV 数据 CSV, matplotlib PNG
│   └── workflow/
│       ├── config.py           # YAML 配置解析/校验
│       ├── runner.py           # 端到端流水线编排
│       └── cli.py              # `cfet-tcad run <config.yaml>`
├── configs/
│   ├── nsheet_nfet_2d.yaml     # nFET 纳米片 (CFET 上层管) 示例
│   └── nsheet_pfet_2d.yaml     # pFET 纳米片 (CFET 下层管) 示例
├── examples/
│   ├── run_idvg.py             # Id-Vg 扫描 + Vt/SS 提取
│   └── run_idvd.py             # Id-Vd 输出特性
└── tests/
    ├── test_geometry.py        # gmsh 几何生成、物理组命名
    ├── test_mesh_loading.py    # devsim 网格加载、区域/接触完整性
    ├── test_extract.py         # 合成数据上的 Vt/SS/DIBL 提取
    └── test_solve_smoke.py     # 粗网格平衡态求解冒烟测试
```

### 关键技术要点

1. **网格格式**：devsim 的 gmsh 读取器只支持 MSH 2.2 ASCII —— gmsh 侧必须 `gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)`。
2. **2D 器件结构**（沿沟道纵截面，双栅近似 GAA）：Si 沟道（本征/轻掺杂，厚度 t_si≈5nm）、两侧重掺杂源/漏延伸区、上下对称栅氧（SiO2，EOT≈0.8nm）、上下金属栅接触、S/D 欧姆接触。物理组命名规范固定（region: channel/source/drain/oxide_top/oxide_bottom；contact: gate_top/gate_bottom/source/drain；interface: si_ox_*），loader 据此加载。
3. **物理方程组织**：参照 devsim 自带 `devsim.python_packages.simple_physics` 的模式自写（不直接依赖它，因为要扩展迁移率模型）：单位用 cm 基准；先解 potential-only（非线性 Poisson，载流子用准费米近似表达），收敛后切换耦合 DD。
4. **栅接触**：金属栅在氧化层上，只参与 Poisson 方程，接触电位 = 偏压 + 功函数差（nFET/pFET 用不同功函数实现 Vt 对称，配置可调）。
5. **收敛性**：开 `set_parameter(name="extended_solver", value=True)` 等扩展精度选项；偏压斜坡自适应步长（失败减半、重试，低于最小步长报错）。
6. **VisIt 对接**：`write_devices(format="vtk")` 每个偏压点输出 .vtu，另生成 .pvd 索引文件组织偏压序列；README 写明 VisIt 打开方式（本容器无法运行 VisIt GUI，验证止于生成合法 VTK 文件）。
7. **Phase 2/3 预留**：`geometry/` 中几何构建器以抽象基类定义接口（build → 物理组命名协定），3D GAA/CFET 堆叠为后续新增子类；`physics/equations.py` 预留 density-gradient 修正的挂载点（文档注明，不实现）。

### 实施步骤

1. 建包骨架：`pyproject.toml`（依赖 + CLI entry point）、目录结构、README 初稿
2. `geometry/`：DeviceParams + gmsh 2D 纳米片构建器，能生成合法 .msh（2.2 ASCII），网格在沟道/氧化层局部加密
3. `meshio_devsim/loader.py`：加载进 devsim，建 device
4. `physics/`：材料库 → 掺杂 → Poisson 方程组 → DD 方程组 → 迁移率模型 → 界面/接触
5. `solve/`：平衡态求解 + 偏压扫描驱动
6. `extract/` + `io/`：参数提取、CSV/PNG/VTK 输出
7. `workflow/`：YAML 配置 + runner + CLI
8. `configs/` + `examples/`：nFET/pFET 示例配置，端到端跑通 Id-Vg、Id-Vd
9. `tests/`：pytest 全套
10. README 完善，提交并推送到 `claude/cfet-tcad-simulation-zh2kfo` 分支

### 验证方案

1. `pip install devsim gmsh numpy scipy matplotlib pyyaml pytest` 后 `pip install -e .`
2. `pytest tests/` 全部通过
3. 端到端：`cfet-tcad run configs/nsheet_nfet_2d.yaml` 生成：
   - Id-Vg 数据 CSV + PNG（曲线呈现正常的亚阈值指数区 + 线性区）
   - 提取结果 JSON：Vt 在合理范围（~0.2–0.4V）、SS ≥ 60mV/dec 且 < 80mV/dec（短沟道 2D 双栅的合理值）、Ion/Ioff
   - .vtu/.pvd 文件（用 Python 读回校验结构合法，即 VisIt 可打开）
4. pFET 配置同样跑通（对称性检查：Vt 为负、电流方向正确）

**结果**：按此蓝图落地 Phase 1（提交 `e50b8ee`，2D 双栅纳米片全流水线），Phase 2/3 依后续各计划推进；仓库骨架、命名契约、配置驱动架构沿用至今。

---

## CFET TCAD — Phase 2 续：Density-Gradient 量子修正

### Context

项目前两轮已完成：Phase 1（2D 双栅纳米片全流程，SS 74/DIBL 90）和 Phase 2 的
3D GAA 单纳米片（SS 76/DIBL 97），均已推送到 `claude/cfet-tcad-simulation-zh2kfo`。
23 个测试通过。

本轮实现路线图中 Phase 2 的剩余关键项：**density-gradient (DG) 量子修正**。
t_si=5nm 的纳米片沟道中量子限域使反型载流子峰值离开界面（体反型）、Vt 正移
数十 mV——Sentaurus 仿真此类器件时默认开 eQuantumPotential/DG。这是经典 DD
与 Sentaurus 结果差距最大的一项物理。

### 物理与离散化方案

**模型**（Bohm 量子势，每种载流子一个新求解变量，仅硅区）：

- 电子：`n = n_i·exp((ψ − Λ_n − φ_n)/V_t)`，`Λ_n = −2·b_n·∇²√n/√n`，
  `b_n = γ_n·ħ²/(12·q·m0·m_dg_n)`；空穴对称（`ψ + Λ_p`）。
- 求解变量集从 (ψ, n, p) 扩展为 (ψ, n, p, Λ_n, Λ_p)，全耦合 Newton。

**DEVSIM 装配**（遵循既有 node_model + edge_model 约定，`∫NM + Σ EM·ec = 0`）：

- DG 方程（对称化通量形式，避免 √n→0 除法）：
  - `NM = Lambda_n * sqrt(Electrons)`
  - `EM = 2*b_n*(sqrt(Electrons@n1) − sqrt(Electrons@n0))*EdgeInverseLength`
  - 导数：NM 对 (Lambda_n, Electrons)，EM 对 Electrons（区域内上下文感知
    diff() 自动链式，模式与既有代码一致）
- SG 电流改用载流子有效势：新增独立边模型 `vdiff_n = ((Potential−Lambda_n)@n0
  − (Potential−Lambda_n)@n1)/V_t`、`Bern01_n = B(vdiff_n)`（+手写导数模型，
  含对 `Lambda_n@n0/@n1` 的导数，模式同 `_create_bernoulli`）；空穴对称。
  电流表达式的 `CreateEdgeModelDerivatives` 变量列表加上 Lambda。
- 边界条件：源/漏接触 `Λ = 0`（contact_equation node_model="Lambda_n"）；
  Si/SiO2 界面自然零通量（Neumann）。**已知局限**：不含氧化层势垒穿透，
  界面排斥弱于 Sentaurus 完整 DG，README 明确记录；扩展方向为氧化层内 DG。
- 经典路径完全不变：`quantum_model: none`（默认）时行为与现状逐位一致。

**收敛策略**：经典 DD 平衡态收敛后再创建 DG 方程（Λ 初值 0）重解平衡态；
若直接求解失败，对 b 系数做同伦（`dg_scale` 参数 0.1→0.3→1.0 逐步重解）。

### 文件改动

| 文件 | 改动 |
|---|---|
| `src/cfet_tcad/physics/quantum.py` **新增** | `create_density_gradient(device, region, mat, ...)`: Λ 解变量/方程/接触 BC；b 系数参数 |
| `src/cfet_tcad/physics/equations.py` | `create_silicon_dd(..., quantum=False)`: quantum 时创建 `vdiff_n/Bern01_n`、`vdiff_p/Bern01_p`（含 Λ 导数），电流用之；`create_ohmic_dd_contact` 增加 Λ=0 接触方程（quantum 时） |
| `src/cfet_tcad/physics/materials.py` | `SemiconductorParams` 增加 `m_dg_n=0.3, m_dg_p=0.4`；ħ 常数 |
| `src/cfet_tcad/solve/initial.py` | `setup_equilibrium(..., quantum_model="none")`: DD 平衡态后按需挂 DG + 同伦重解 |
| `src/cfet_tcad/workflow/config.py` | `PhysicsConfig.quantum_model: "none"/"density_gradient"`、`dg_gamma_n/p` |
| `src/cfet_tcad/workflow/runner.py` | 把 quantum 配置透传给 setup_equilibrium |
| `configs/nsheet_nfet_2d_dg.yaml` **新增** | 与 nsheet_nfet_2d.yaml 同器件 + DG 开启（直接对比 Vt 偏移） |
| `tests/test_quantum.py` **新增** | 粗网格 DG 平衡态收敛；Λ_n 场非平凡；与经典解对比界面载流子密度降低 |
| `README.md` | 物理模型/路线图/局限说明更新 |

复用：`model_create` 辅助函数、`CreateEdgeModelDerivatives` 的上下文感知
diff() 模式、既有同伦式偏压斜坡骨架、`fresh_devsim`/`cfet_tcad.reset()`
测试基建。

### 验证

1. `pytest tests/` 全部通过（新增 DG 测试，经典路径测试不回归）。
2. 端到端 `cfet-tcad run configs/nsheet_nfet_2d_dg.yaml`：
   - 收敛完成 Id-Vg 双 Vd 扫描；
   - 对比经典 fom.json：**Vt 正移 +20~60mV**、SS 变化不大（±3mV/dec）、
     Ion 略降 —— 方向与量级符合 DG 物理预期；
   - VTK 输出含 Lambda_n 场（VisIt 可视化量子势分布）。
3. （快速抽查）DG 也能在 3D GAA 上收敛（粗网格平衡态即可，不跑全扫描）。
4. 提交并推送。

**结果**：提交 `0dd234c`。实现中发现并解决 Robin 氧化物界面项方向、√(n+1) 正则化、各向异性 DG 权重、仅输运载流子求解四个关键问题（详见提交信息与 PROJECT_DEV_PLAN Phase 2）。

---

## CFET TCAD — Phase 3 续：CFET 反相器 VTC（电路节点耦合）

### Context

前四轮已完成：Phase 1（2D 双栅全流程）、Phase 2（3D GAA + density-gradient
量子修正）、Phase 3 核心（CFET 堆叠共栅联合求解，`cfet_idvg` 实验，堆叠内
单管指标与独立仿真逐位一致）。30 测试全过，已推送。

本轮实现 CFET 作为 CMOS 单元的标志性仿真：**反相器电压传输特性 (VTC)**。
nFET 漏与 pFET 漏连到同一浮空输出节点 Vout，Vout 由两管电流平衡自洽决定
—— 用 DEVSIM 内置电路求解器（`circuit_element` + `contact_equation` 的
`circuit_node` 耦合，混合器件/电路 Newton），对标 Sentaurus 的 mixed-mode
仿真能力。

### 技术方案

**电路耦合**（模式参照 devsim 自带 `simple_physics` 的 `is_circuit=True`
分支，见 `/usr/local/lib/python3.11/dist-packages/devsim/python_packages/
simple_physics.py` 第 221-241、363-380 行）：

- 创建电路节点 `vout`：`circuit_element(name="R1", n1="vout", n2=0,
  value=1e15)` —— 超大电阻到地既创建节点又给平衡态一个确定解（Vin=0
  平衡态时两管电流为零，无载荷则 vout 不定）。
- `drain_n`、`drain_p` 两个接触改为电路接触：
  - 接触电位模型引用 `vout` 符号（替代 `{contact}_bias` 参数）+
    手写导数模型 `{model}:vout = -1`；
    `contact_equation(..., name="PotentialEquation", circuit_node="vout")`
  - ECE/HCE 的 `contact_equation(..., circuit_node="vout")` —— 两管漏电流
    注入 vout 的 KCL 行，Newton 同时解出器件场量与 vout。
- 其余接触保持参数偏压：source_n=0、source_p=Vdd、四栅=Vin。
- 读回：`get_circuit_node_value(node="vout")`。

**求解序列**：正常平衡态装配（drains 即为电路接触，vout 初值 0）→
ramp source_p → Vdd（vout 被 pFET 拉到 ≈Vdd）→ 扫 Vin 0→Vdd，每点记录
vout 与电源电流（short-circuit current）。

### 文件改动

| 文件 | 改动 |
|---|---|
| `physics/equations.py` | `create_ohmic_potential_contact` / `create_ohmic_dd_contact` 增加可选 `circuit_node` 参数（模式抄 simple_physics is_circuit 分支） |
| `solve/initial.py` | `setup_equilibrium(..., circuit_contacts: dict = {})`：装配时对指定接触走电路分支 |
| `workflow/runner.py` | 新实验 `run_cfet_vtc`：建 R1/vout、装配、ramp Vdd、扫 Vin 记录 (vin, vout, i_dd)、绘图/CSV/JSON |
| `extract/figures_of_merit.py` | `extract_vtc_fom(vin, vout, vdd)`：VM（vout=vin 交点）、最大增益、VIL/VIH（增益=1 点）、噪声容限 NML/NMH |
| `workflow/config.py` | simulation.type 增加 `cfet_vtc` |
| `configs/cfet_vtc_2d.yaml` **新增** | 与 cfet_2d.yaml 同器件，type: cfet_vtc |
| `tests/test_vtc.py` **新增** | 合成 VTC 提取（已知 VM/增益）；粗网格 CFET+电路平衡态收敛且 Vin=0 时 vout≈Vdd |
| `README.md` | 快速开始 + 路线图勾选 |

复用：CFETStack2DBuilder、setup_equilibrium 全部物理、ramp_biases、
plot 基建、fresh_devsim。

### 验证

1. `pytest tests/` 全过（新增 VTC 测试，无回归）。
2. 端到端 `cfet-tcad run configs/cfet_vtc_2d.yaml`：
   - VTC 呈 S 形：Vin=0 → Vout≈0.7V；Vin=0.7 → Vout≈0V；
   - VM ≈ 0.33V（与 cfet_idvg 交越点一致）、最大增益 >> 1、
     NML/NMH 合理（各 ~0.2-0.3V）；
   - 电源电流呈钟形（VM 附近短路电流峰值）；
   - vtc.png / vtc.csv / fom.json / VTK 输出齐全。
3. 提交并推送。

风险：电路接触的 contact_equation 参数细节、浮空节点首个平衡态的收敛
—— 按既往方式交互式调试；R1=1e15Ω 若不足以稳定可降至 1e12Ω。

**结果**：提交 `3878ff5`。VTC 满摆幅、VM=0.338V 与 cfet_idvg 电流交越点一致，NML/NMH≈0.30/0.32V。

---

## CFET TCAD — Lombardi 垂直场迁移率退化（element 级装配）

### Context

七轮已交付完整系统（2D/3D/CFET 堆叠、DG 量子修正、混合电路 VTC、并行
DOE，40 测试全过）。剩余物理项中最重要的是 **Lombardi (CVT) 垂直场迁移率
退化**：表面声子散射 + 表面粗糙度散射使反型层迁移率随垂直场衰减。当前
系统的 Ion（~950µA/µm 级）明显乐观正是因为缺这项——Sentaurus 仿真 MOS
类器件默认开启 CVT。这是与 Sentaurus 的最后一个主要物理差距。

技术难点：垂直场 E⊥ 需要**矢量场重构**，超出边（edge）标量模型的能力，
必须用 DEVSIM 的 element（单元）级装配：电流从 edge 模型换成 element
模型。API 已确认可用：`element_from_edge_model(derivative=)` 生成场的
方向分量及导数、`equation(element_model=)`、
`contact_equation(element_current_model=)`；`model_create` 已有
`CreateElementModel2d` / `CreateElementModelDerivative2d` 辅助函数。

### 物理模型（简化 CVT，Matthiessen 合成）

每条 element edge 上：

- 场重构：`element_from_edge_model("ElectricField")` → `ElectricField_x/y`
  （element 模型，含对 Potential 的导数版本）；
  `E⊥ = sqrt(max(E² − (E·û)², ε))`，û = (unitx, unity) 边方向余弦，
  ε=1e-4 保持可微（同既有 Epar 正则化手法）。
- CVT 分量（Si 经典参数）：
  - 声子项 `μ_ac = B/E⊥`（电子 B=4.75e7、空穴 9.925e6 cm/s；
    简化掉弱的掺杂/温度依赖项）
  - 粗糙度项 `μ_sr = δ/E⊥²`（电子 δ=5.82e14、空穴 2.055e14 cm²/Vs）
- 合成：`1/μ_lombardi = 1/μ_lf + 1/μ_ac + 1/μ_sr`（μ_lf 为既有掺杂
  依赖边模型，element 上下文可直接引用）+ 既有 Caughey-Thomas 速度饱和
  （E∥ 用边方向场，element 表达式内联）。
- SG 电流公式不变，但作为 **element 模型**创建（Bern01/vdiff 等边模型在
  element 上下文可引用），导数用 `CreateElementModelDerivative2d`
  （@en0/@en1/@en2）对 Potential/Electrons/Holes。
- 方程重接线：`equation(..., edge_model="", element_model="ElectronCurrentE")`
  与 `contact_equation(..., element_current_model=...)`。
  `get_contact_current` 对 element 电流同样有效（KCL 装配一致）。

### 文件改动

| 文件 | 改动 |
|---|---|
| `physics/lombardi.py` **新增** | E⊥ 重构、CVT 迁移率 element 模型、element SG 电流 + 导数、方程/接触重接线函数 |
| `physics/mobility.py` | `MOBILITY_MODELS` 增加 `"lombardi_vsat"`；CVT 参数进 `materials.py`（SemiconductorParams 增加 B/δ 字段） |
| `solve/initial.py` | mobility_model=="lombardi_vsat" 时：常规 DD 装配收敛后调用 lombardi 重接线并重解（沿用 DG 的"先经典后增强"套路）；限 2D 硅区（3D 报 NotImplementedError）；与 quantum_model 组合暂拒绝（element 量子电流留后续） |
| `workflow/config.py` | 校验放行新模型名 + lombardi×DG 组合校验 |
| `configs/nsheet_nfet_2d_lombardi.yaml` **新增** | 与基准 nFET 同器件 + lombardi_vsat |
| `tests/test_lombardi.py` **新增** | CVT 公式单值检查；粗网格平衡态+短扫描收敛；Ion 显著低于 doping_vsat 而亚阈值区（低场）电流基本不变 |
| `README.md` | 物理说明、Ion 修正幅度、路线图勾选 |

复用：`_create_bernoulli`/SRH/接触装配全部不动（只换电流模型）；
`model_create` element 辅助函数；DG 的分阶段重解模式。

### 实施步骤（增量验证）

1. 交互式最小实验：1 个粗 2D 器件上验证 element 场重构数值（E⊥ 在栅下
   ≈ Ey，S/D 区 ≈ 0）→ 再建 element SG 电流并与 edge 电流在同一状态下
   数值对照（μ 相同时应逐位一致）→ 最后换 CVT 迁移率。
2. 按上表落文件；平衡态后重接线重解。
3. e2e 对比 doping_vsat：预期 Ion 下降 ~30-50%（低 Vg 区不变、SS 不变、
   高 Vg 区增益压缩），曲线形态正确。
4. 全套 pytest + 提交推送。

### 验证

1. element SG 电流与 edge SG 电流的一致性对照（相同 μ 下 Id 相对差 <1e-10）
   —— 这是 element 装配正确性的强校验。
2. `cfet-tcad run configs/nsheet_nfet_2d_lombardi.yaml`：收敛完成双 Vd
   扫描；对比基准 fom.json：Ion ↓30-50%、SS/Vt 基本不变、Ioff 基本不变。
3. `pytest tests/` 全过（新增 lombardi 测试）。

### 风险与回退

element 电流的 Newton 收敛是主要风险（Jacobian 更稠密）。回退阶梯：
(a) 收敛难 → 迁移率中 E⊥ 用 lag（上一步解）？不做——devsim 无 lag 机制，
改为把 CVT 项乘 homotopy 系数（复用 dg_scale 模式，`cvt_scale` 0→1）；
(b) 若 element 装配根本性受阻 → 记录结论并保留分支，不合入主线。

**结果**：提交 `51f043a`（2D）；后续 `0813011` 扩展到 3D 四面体element 装配。@en* 独立符号求导语义是此计划实现中的关键发现。

---

## CFET TCAD — element 级量子电流（解除 CVT×DG 互斥，"全物理"配置）

### Context

十轮已交付完整系统（48 测试全过）。当前限制：`lombardi_vsat`（element
电流）与 `density_gradient`（edge 量子电流）互斥，因为两者改写同一套
SG 电流但离散化不同。本轮把量子有效势并入 element 电流，使
**CVT + DG 可同开**——这正是 Sentaurus 仿真先进节点器件的默认物理组合，
补齐后系统的"全物理"工况成立。

### 技术方案

关键点：DG 的 Λ_n/Λ_p **方程**（quantum.py 的对称化边通量形式 + Robin
界面项 + 各向异性权重）与电流离散化无关，完全不动。要改的只是 element
SG 电流的 Bernoulli 驱动势：量子载流子改用有效势（电子 ψ−Λ_n、空穴
ψ+Λ_p）。element 表达式全内联 + 上下文感知 diff ⇒ 无需手写导数模型
（比 edge 版量子电流更简单），只需把 Λ 加进导数变量表（@en0..@enN）。

**装配顺序**（setup_equilibrium，两者同开时）：

1. 经典 DD（doping 迁移率，edge 电流）→ 求解；
2. Lombardi element 重接线（经典势）→ `cvt_scale` 同伦至 1；
3. DG：`create_density_gradient` + `create_dg_contact`（原样）→
   **重建 element 电流为量子版**（同名替换 `ElectronCurrentE`/
   `HoleCurrentE`，方程/接触已按名引用，无需重接线）→ `dg_scale` 同伦。

CVT 迁移率的驱动场保持静电场（E⊥/E∥ 不含 Λ），与 Sentaurus 实践一致。

### 文件改动

| 文件 | 改动 |
|---|---|
| `physics/lombardi.py` | `apply_lombardi_currents(..., quantum_carriers=())`：按载流子选择 vdiff 表达式（经典 ψ 或有效势 ψ∓Λ 内联文本），量子载流子的导数变量表加 `Lambda_n`/`Lambda_p` |
| `solve/initial.py` | 删除组合 ValueError；quantum 阶段若 lombardi 生效则调用 `apply_lombardi_currents(quantum_carriers=...)` 替代 edge 版 `apply_quantum_currents`（DG 方程/接触创建不变，dg_scale 同伦不变） |
| `workflow/config.py` | 删除 lombardi×DG 组合校验 |
| `configs/nsheet_nfet_2d_full.yaml` **新增** | 全物理配置：lombardi_vsat + density_gradient（与基准同器件） |
| `tests/test_lombardi.py` | 组合拒绝测试 → 组合收敛测试（粗网格 2D：CVT+DG 平衡态收敛、Λ 非平凡、mu_n_cvt 退化并存） |
| `README.md` | 全物理说明、互斥说明删除、路线图勾选 |

复用：quantum.py 全部原样；`_solve_scale_homotopy`；element 导数辅助。

### 验证

1. `pytest tests/` 全过（组合测试新增，无回归；lombardi-only 与 DG-only
   行为不变）。
2. 端到端 `cfet-tcad run configs/nsheet_nfet_2d_full.yaml` 并与三个基准
   对比（doping_vsat 经典 / lombardi-only / DG-only 的既有 fom.json）：
   - 收敛完成双 Vd 扫描；
   - 组合效应方向自洽：Vt 正移（≈DG-only 的偏移）、线性区 Ion 低于
     lombardi-only（两种退化叠加）、SS/DIBL 基本不变；
   - 组合的各单项效应与单开时同量级（无病态串扰）。
3. （抽查）3D GAA 上 CVT+DG 组合平衡态收敛。
4. 提交推送。

### 风险与回退

dg_scale 同伦叠加在 element 电流上是新组合，收敛风险中等；既有二分同伦
阶梯覆盖。若 Λ 与 CVT 迁移率在高偏压下交互失稳，退一步的选项是量子载流
子的 vsat 项改用有效势场（更一致的驱动力定义）——按需再调。

**结果**：提交 `5a8f6ae`。CVT×DG 互斥解除，'全物理'配置 nsheet_nfet_2d_full.yaml 上线。

---

## CFET TCAD — SiGe(x) 组分插值 + 成组参数 DOE

### Context

十一轮已交付全物理系统（48 测试全过）。SiGe 目前是单点硬编码
（SiGe30），本轮把 Ge 组分变成**连续设计变量**：参数化材料工厂
`sige(x)` + 材料名动态解析（`SiGe15`→x=0.15），并给 sweep 引擎补
**成组参数**能力（`--zip`：多个 -p 同步推进而非笛卡尔积——SiGe 组分
扫描必须同步重调栅功函数以保持等 Vt，否则 Eg(x) 变化污染对比，这正是
上轮 SiGe 验证学到的教训）。交付物：Ge 组分 DOE 研究（pFET 驱动与 n/p
平衡 vs x 曲线）。

其余两个路线图项本轮不做并在 README 说明理由：多纳米片网格化在接触终
结栅模型下与 `n_sheets` 电流缩放严格等价（CFET 堆叠逐位交叉验证已证）；
氧化层内 DG 的精度增益已被 `dg_gamma` 标定旋钮覆盖。

### 技术方案

**材料工厂**（physics/materials.py）：

- `sige(x)`：应变 Si₁₋ₓGeₓ 参数线性插值，锚定现有 SiGe30 数值使
  `sige(0.30) == SIGE30`（单一真源：SIGE30 改由工厂生成）：
  - `Eg = 1.12 − 0.467x`；`n_i = n_i_Si·exp((1.12−Eg)/(2kT/q))`（300K）
  - `eps_r = 11.7 + 1.67x`；`mu_max_p = 470.5 + 1432x`；
    `mu_max_n = 1414 − 1380x`；vsat/CVT/DG 参数保持 Si 值（标定旋钮）
  - 校验 0 ≤ x ≤ 0.5（Si 上应变的实用范围）
- `get_material(key)`：精确命中 MATERIALS，否则正则解析 `SiGe(\d+)` →
  `sige(x/100)`；无法解析报既有的 ValueError 文案。
  `solve/initial.material_of` 改用 `get_material`。

**成组参数 sweep**（workflow/sweep.py + cli.py）：

- `run_sweep(..., zip_params=False)`：True 时要求所有参数值列表等长，
  逐位配对生成点（替代 itertools.product）。
- CLI `cfet-tcad sweep ... --zip`。
- 趋势图条件放宽：zip 模式下若**第一个**参数为数值则以其为 x 轴。

**Ge 组分 DOE**（验证交付）：cfet_2d_sige.yaml 基线上
`-p device.channel_material_p=Silicon,SiGe15,SiGe30,SiGe45
 -p device.gate_workfunction_p_ev=4.72,4.655,4.59,4.525 --zip -j 4`
（WF 按 −0.13/0.3x 线性重调保持等 Vt）。汇总后小脚本绘制
Ion_p / n:p 平衡 vs x。

### 文件改动

| 文件 | 改动 |
|---|---|
| `physics/materials.py` | `sige(x)` 工厂、`get_material(key)`、SIGE30=sige(0.30) |
| `solve/initial.py` | `material_of` 用 `get_material` |
| `workflow/sweep.py` | `zip_params` 支持 + 趋势图 x 轴选择 |
| `workflow/cli.py` | `--zip` 选项 |
| `tests/test_materials.py` | 工厂插值锚点（sige(0.3)==SiGe30、sige(0)≈Si）、动态解析、越界拒绝 |
| `tests/test_sweep.py` | zip 配对单元测试（长度不等拒绝、点数正确） |
| `README.md` | 材料插值说明、--zip 说明、路线图收尾（含不做项的理由） |

复用：sweep 引擎全部、SiGe 验证一轮建立的 WF 重调方法。

### 验证

1. `pytest tests/` 全过。
2. Ge 组分 DOE（4 点 ×4 并行，约 2-3 分钟）：Ion_p 与 n/p 平衡随 x
   单调上升；x=0.30 点与上轮 run_sige2 结果一致（回归锚点）；
   等 Vt 约束成立（各点 Vt_p ≈ −0.38±0.01）。
3. 绘制并交付 balance-vs-x 曲线。
4. 提交推送。

**结果**：提交 `32b46b5`。sige(x) 连续插值 + --zip 成组 DOE；Ge 组分扫描示例（含逐组分功函数重调保持等 Vt）进入 README。

---

## CFET TCAD — PySide6 桌面 UI（对标 Sentaurus Workbench）

### Context

十二轮已交付完整命令行系统（50 测试、15 验证配置）。本轮加 **PySide6
图形界面**，交互范式对标 Sentaurus Workbench (SWB)：

- **实验表格**（SWB 的标志）：行 = 实验点，列 = 关键参数 + 状态 + 提取
  结果；状态色块随运行流转（灰=排队、黄=运行中、绿=完成、红=失败）；
- **参数编辑器**（对标 SWB 工具参数面板）：从配置 dataclass 自动生成
  表单，加载/保存 YAML；
- **结果查看器**（对标 Sentaurus Visual/Inspect 的曲线部分）：
  matplotlib 画布交互重绘 CSV 曲线（log/linear 切换）+ FOM 表；
- **日志控制台**：求解器输出实时滚动。

工程约束与决策：

1. DEVSIM 全局状态 ⇒ 仿真必须独立进程。GUI 用 **QProcess 驱动既有
   CLI**（`cfet-tcad run/sweep`），零侵入复用全部后端；扫描在 GUI 内
   展开为逐点任务队列（限并发），使表格行逐个变绿——还原 SWB 体验。
2. 本容器无显示器 ⇒ 开发/测试/验证全程用 `QT_QPA_PLATFORM=offscreen`；
   交付证据 = `QWidget.grab()` 截图（含运行前/中/后状态）发给用户。
3. GUI 为可选依赖（`pip install -e '.[gui]'`，PySide6-Essentials），
   不影响无 GUI 环境；核心包不 import Qt。

### 界面布局（SWB 风格）

```
┌ 工具栏: [Run] [Sweep...] [Stop] [Open Results]  ──────────────┐
├───────────┬──────────────────────────────────────────────────┤
│ 配置列表   │  Tab1: Experiments(实验表格: 参数列|状态|Vt/SS/  │
│ configs/  │        Ion/Ioff 列, 行双击打开结果)               │
│ *.yaml    │  Tab2: Parameters(dataclass 表单, Save/Save As)  │
│           │  Tab3: Results(matplotlib 曲线 + FOM 表)          │
├───────────┴──────────────────────────────────────────────────┤
│ 日志控制台 (QPlainTextEdit, 求解器 stdout 实时 tail)           │
└───────────────────────────────────────────────────────────────┘
```

### 文件结构

```
src/cfet_tcad/gui/
├── __init__.py
├── app.py               # main(): QApplication + MainWindow; 入口 cfet-tcad-gui
├── main_window.py       # 布局/工具栏/信号接线
├── config_form.py       # dataclasses.fields → 表单(QLineEdit/QComboBox/
│                        #   QCheckBox); 枚举字段(structure/mobility_model/
│                        #   quantum_model/materials)用下拉; YAML 读写
│                        #   (复用 workflow.config 的 build_config 校验)
├── experiment_table.py  # ExperimentModel(QAbstractTableModel):
│                        #   行={名称,覆盖参数,状态,fom 摘要}; SWB 状态色
├── run_queue.py         # RunQueue: QProcess 池(限并发) 执行
│                        #   `cfet-tcad run <yaml> -o <dir>`; 扫描点 =
│                        #   apply_overrides 写临时 YAML(复用 sweep 的
│                        #   parse_param_spec/apply_overrides); 完成回调
│                        #   读 fom.json 回填表格
├── results_view.py      # FigureCanvasQTAgg 重绘 idvg/idvd/vtc CSV
│                        #   (log/lin 切换) + FOM QTableWidget
└── log_console.py
tests/test_gui.py        # offscreen: 窗口构建、表单↔YAML 往返、
                         #   表格模型状态流转(mock 进程)
```

pyproject: `[project.optional-dependencies] gui = ["PySide6-Essentials"]`；
`[project.scripts] cfet-tcad-gui = "cfet_tcad.gui.app:main"`。

复用清单：`workflow.config.load_config/build_config/apply_overrides`、
`workflow.sweep.parse_param_spec`、CLI 本身（QProcess 目标）、
`extract` 输出的 fom.json 结构、CSV 格式。

### 实施步骤

1. `pip install PySide6-Essentials` + 所需系统库（libegl1/libxkbcommon
   等按报错补），offscreen 平台冒烟确认。
2. 按上表落文件：先 ExperimentModel/RunQueue（核心逻辑，可单测），
   再表单/结果视图，最后 main_window 组装。
3. offscreen 端到端脚本验证：加载 nsheet_nfet_2d.yaml → 改 vg_step=0.1
   缩短运行 → 入队运行 → 等 QProcess 完成 → 断言行状态=done、FOM 回填
   → 截图（Experiments/Parameters/Results 三个 Tab）交付。
4. `pytest`（GUI 测试用 importorskip，保证无 PySide6 环境不受影响）。
5. README 增加 GUI 章节 + 截图说明，提交推送。

### 验证

1. offscreen 端到端：真实跑一个短仿真，表格状态 灰→黄→绿 流转、
   FOM 列回填、Results 页曲线/FOM 表正确加载。
2. 三张界面截图（QWidget.grab）作为交付证据发用户。
3. `pytest tests/` 全过（新增 GUI 测试；核心 50 项不回归）。
4. 无 GUI 依赖环境 `import cfet_tcad` 与 CLI 不受影响（gui 子包惰性）。

### 风险

- 容器无显示 ⇒ 所有验证走 offscreen，真机观感留待用户本地
  `pip install -e '.[gui]' && cfet-tcad-gui`；
- PySide6 轮子较大（~150MB），安装耗时可接受；
- matplotlib qtagg 后端与 PySide6-Essentials 兼容性——若有问题退回
  在 GUI 内嵌 Agg 渲染的 QPixmap（功能等价，少交互缩放）。

**结果**：提交 `5297edb`。五大功能区 + QProcess 进程池 + SWB 状态色块交互全部落地。

---

## CFET TCAD — 3D 器件结构渲染（Structure 视图，对标 SDE/Sentaurus Visual 3D）

### Context

GUI 已具备实验表格/参数/曲线三视图，缺 3D 结构可视化。用户问"能否看到
渲染的 3D 器件图"——本轮补上：**PyVista**（VTK 渲染引擎，与 Sentaurus
Visual 同技术栈）读取系统已产出的 `.vtu` 文件做真 3D 渲染，嵌入 GUI 为
Structure 页；容器无显示器用 Xvfb（已装）离屏渲染 PNG 作为交付证据。

可行性已确认：pyvista 0.48.4 / pyvistaqt 0.12.0 在 PyPI 可装，
`xvfb-run` 可用，且 run_cfet3d / run_gaa3d 的 3D VTK 数据已存在。

### 功能设计

1. **结构快照命令**（对标 SDE"只看结构不求解"）：
   `cfet-tcad structure <config.yaml> -o <dir>`——建网格 → devsim 加载 →
   仅创建掺杂节点模型（不装配方程不求解，~几秒）→ `write_devices` 输出
   各 region 的 .vtu。GUI 里通过 QProcess 调用（devsim 全局状态）。
2. **渲染模块** `src/cfet_tcad/io/render3d.py`（不依赖 Qt，可独立用）：
   - `load_device_mesh(vtk_dir, tag=None)`：收集一个输出目录的 region
     .vtu（devsim 命名 `<prefix>_<n>.vtu`，用 .vtm 索引或 glob）；
   - `render_structure(vtk_dir, png=None, field=None, clip=None,
     plotter=None)`：region 按材料着色（硅色/氧化物半透明），或按
     `field`（NetDoping 对称对数色标、Potential/Electrons 等）着色；
     `clip="y"/"z"` 剖切露出内部沟道；无 `plotter` 时离屏渲染到 png。
3. **GUI Structure 页** `src/cfet_tcad/gui/structure_view.py`：
   - pyvistaqt `QtInteractor` 交互 3D（旋转/缩放）；
   - 控件：字段下拉（Structure/NetDoping/Potential/Electrons/Lambda_n）、
     剖切开关、快照序号（偏压点）选择；
   - 数据源：双击实验行时若其 out_dir 有 vtk/ 则加载末偏压点快照；
     工具栏新增 "Structure" 按钮→对当前配置跑 structure 快照并显示；
   - pyvista 未安装时显示提示标签（优雅降级，gui 核心不依赖 viz）。
4. 依赖：`[project.optional-dependencies] viz = ["pyvista", "pyvistaqt"]`；
   README 说明 `pip install -e '.[gui,viz]'`。

### 文件改动

| 文件 | 改动 |
|---|---|
| `src/cfet_tcad/io/render3d.py` **新增** | vtu 收集 + pyvista 场景构建/着色/剖切/离屏截图 |
| `src/cfet_tcad/workflow/cli.py` | `structure` 子命令（复用 BUILDERS/load_mesh/create_doping/write_devices） |
| `src/cfet_tcad/gui/structure_view.py` **新增** | QtInteractor 页 + 字段/剖切控件 + 优雅降级 |
| `src/cfet_tcad/gui/main_window.py` | 加 Structure 页、工具栏按钮、行双击联动 |
| `pyproject.toml` | viz extra |
| `tests/test_render3d.py` **新增** | importorskip(pyvista)：结构快照 CLI 产出 vtu；离屏渲染 PNG 非空且尺寸正确；2D 结构也可渲染（平面网格） |
| `README.md` | Structure 视图章节 |

复用：`geometry.BUILDERS`、`meshio_devsim.load_mesh`、
`physics.doping.create_doping`、devsim `write_devices`、GUI 既有
QProcess/表格联动模式。

### 验证（本轮交付给用户的核心）

1. 容器内 `xvfb-run` 渲染并发送 PNG：
   - **3D CFET 堆叠结构图**（材料着色 + 剖切露沟道）——用户所问的图；
   - 3D GAA 的 **Potential 场体渲染**（ON 态快照）；
   - GUI Structure 页嵌入渲染的整窗截图（offscreen/xvfb）。
2. `pytest`：新增渲染测试（无 pyvista 环境跳过），既有 56 项不回归。
3. 提交推送。

### 风险

- vtk 离屏后端：优先试 pyvista off_screen 直渲，不行退 `xvfb-run`
  （已确认在系统内）；
- pyvistaqt 与 PySide6-Essentials 兼容性——QtInteractor 只需
  QtWidgets/QtCore/QtGui，Essentials 覆盖；若有缺口退化为"渲染 PNG 显示
  在 QLabel"（仍可换视角按钮驱动重渲，功能保底）。

**结果**：提交 `05a4938`。Structure 3D 标签页 + CLI --png；后续在论文复现阶段又扩展出迁移率场着色与截面切割（`37e27be`）。

---

## CFET TCAD — GitHub Actions 构建 Windows 11 独立 exe

### Context

系统 v0.5 完整（62 测试、CI 已上）。本轮：**GitHub Actions 的
windows-latest 跑道用 PyInstaller 打包独立可执行程序**，Windows 11 免装
Python 直接运行。可行性已确认：devsim/gmsh/PySide6/pyinstaller/mkl 全部
有 win_amd64 轮子（devsim Windows 版依赖 MKL，pip `mkl` 提供 DLL）。

产物形态：**onedir 目录包**（zip 工件），内含两个 exe ——
`cfet-tcad-gui.exe`（窗口程序）与 `cfet-tcad.exe`（命令行）。选 onedir
而非 onefile：VTK+Qt+MKL 体积大（数百 MB），onefile 每次启动解包极慢。
Windows Server 2022 runner 构建的二进制与 Win11 同 ABI。

关键工程点（唯一无法本地验证的环节是 Windows 行为，因此**CI 即测试
环境**，预期需要数轮迭代，用 MCP `actions_run_trigger` 触发 +
后台轮询收敛）：

1. **BLAS 引导的 Windows/frozen 支持**（`src/cfet_tcad/__init__.py`）：
   现有 `_ensure_devsim_math_libs` 只按 Linux 名字找。扩展：
   - Windows：`find_library("mkl_rt")` + 直接 glob `mkl_rt*.dll`
     （mkl 轮子的 DLL 名带版本号如 `mkl_rt.2.dll`，find_library 可能
     找不到）；搜索路径含 `sys.prefix/Library/bin`（pip mkl 安装位）；
   - frozen（`sys.frozen`）：exe 目录 `os.add_dll_directory` + 在其中
     glob mkl/openblas DLL 设置 `DEVSIM_MATH_LIBS`。
2. **PyInstaller spec**（`packaging/cfet_tcad.spec`）：
   - `collect_all("devsim")`（devsim_py3 扩展 + umfpack 子包 DLL）、
     `collect_all("gmsh")`（gmsh-4.x.dll 在包目录，ctypes 加载）、
     `collect_all("pyvista")`/`pyvistaqt`、`collect_data_files("cfet_tcad")`
     （help 指南 + 图片）；PySide6/vtk/matplotlib 走官方 hooks；
   - MKL DLL：从 `sys.prefix/Library/bin` 收集 `mkl_*.dll` 进 binaries；
   - 两个 EXE 共享一份 COLLECT：`cfet-tcad.exe`（console=True，入口
     workflow.cli:main）、`cfet-tcad-gui.exe`（console=False，入口
     gui.app:main）。
3. **工作流**（`.github/workflows/windows-exe.yml`）：
   - 触发：`workflow_dispatch` + `push: tags: v*`（不在每次 push 上跑，
     Windows 构建 ~20 分钟）；
   - 步骤：checkout → Python 3.11 → `pip install -e .[gui,viz] pyinstaller mkl`
     → **Windows 冒烟测试**（`QT_QPA_PLATFORM=offscreen pytest
     tests/test_solve_smoke.py tests/test_gui.py -q`，验证 devsim+MKL、
     Qt 在 Windows 可用）→ `pyinstaller packaging/cfet_tcad.spec`
     → **frozen 冒烟**：`dist/cfet-tcad/cfet-tcad.exe structure
     configs/nsheet_nfet_2d.yaml -o smoke`（验证打包后的
     devsim+gmsh+MKL 链路）+ `cfet-tcad-gui.exe` 帮助性启动检查
     → 压缩 dist → `actions/upload-artifact`；tag 触发时另附加到
     Release（softprops/action-gh-release）。
4. **README**：Windows 下载/运行章节（Artifacts 或 Releases 获取 zip，
   解压运行 cfet-tcad-gui.exe；SmartScreen 提示说明——未签名）。

### 文件改动

| 文件 | 改动 |
|---|---|
| `src/cfet_tcad/__init__.py` | `_ensure_devsim_math_libs` 增加 Windows（mkl_rt glob + Library/bin 路径）与 frozen（exe 目录 DLL）分支 |
| `packaging/cfet_tcad.spec` **新增** | 如上，两 EXE 一 COLLECT |
| `.github/workflows/windows-exe.yml` **新增** | 如上 |
| `README.md` | Windows 独立版章节 |
| `tests/test_bootstrap.py` **新增** | bootstrap 纯逻辑单测（DLL 名匹配函数在 Linux 上可测的部分） |

复用：既有 CLI（frozen 冒烟直接用 structure/run 子命令）、
`actions_run_trigger`/`actions_get` MCP 工具做触发与观测。

### 验证

1. 推送后用 MCP `actions_run_trigger` 触发 workflow_dispatch，后台轮询；
   失败则读 job 日志（`get_job_logs failed_only`）修复迭代，直至绿。
2. 绿后确认工件存在（`list_workflow_run_artifacts`，zip 大小合理
   300MB-1GB），frozen 冒烟步骤日志显示结构导出成功。
3. Linux 全套 pytest 不回归。
4. 报告工件下载路径（Actions run → Artifacts）。

### 风险

- PyInstaller 对 devsim/gmsh 无官方 hook —— collect_all + 显式 DLL
  收集覆盖；若 umfpack ctypes 路径在 frozen 下失效，fallback 是把
  devsim/umfpack 目录整体作为 data 收集（保持相对路径）。
- MKL DLL 名随版本变化 —— glob 而非硬编码。
- 迭代成本：每轮 Windows CI ~15-25 分钟，控制在最少往返（第一轮就带
  齐 spec 的已知收集项 + 冒烟日志尽量详尽）。

**结果**：首版提交 `2b57285`，经 `15f1538`/`93d2e3b`（新增 Nuitka 跑道）/`0fc4026`（无 GL 门控）/`163dfdc`（UTF-8）迭代至双跑道全绿；后续现场问题（非 ASCII 路径、libiomp5md、无控制台 stdio）由独立修复处理（`2cb3059`/`099c282`，未走 plan 模式）。

---

## 设计导入 / 导出：外部网格导入 + CSV 设计点导入 + STL/OBJ 几何导出

### Context

用户问"当前程序支持设计导入和导出功能吗"，答复中给出三个可行扩展后用户回复
"全部都要"：

1. **外部 gmsh `.msh` 导入**（+ 命名映射表）——绕过参数化 builder，直接仿真
   用户自备网格；
2. **CSV 设计点批量导入**到 sweep 引擎——DOE 表格从外部工具（Excel 等）导入，
   与已有的 `sweep_summary.csv` 导出形成闭环；
3. **STL/OBJ 几何导出**——器件三维几何给 CAD/展示用。

现有可复用的关键机制：`meshio_devsim/loader.py::load_mesh` 本就吃任意
MSH 2.2 + `MeshLayout`；`workflow/sweep.py` 的 `--zip` 模式点列表
= CSV 的行；`io/render3d.py::load_snapshot/add_device` 已能重建带
材质配色的 pyvista 场景。

### ① 外部网格导入（structure: external）

**配置**（新 YAML 形态，全部走现有 `device` 区）：

```yaml
device:
  name: my_dev
  structure: external          # 新 structure 值
  polarity: n
  external:                    # 新 dict 字段（其他 structure 下必须为空）
    mesh_file: my_mesh.msh     # MSH 2.2 ASCII；相对路径以配置文件所在目录解析
    dimension: 2
    regions: {bulk: Silicon, gox: Oxide}
    contacts: {source: bulk, drain: bulk, gate: gox}
    interfaces: {si_ox: [bulk, gox]}
    silicon_polarity: {bulk: n}            # 可选，缺省用 device.polarity
    gate_workfunctions: {gate: 4.5}        # 可选
    semiconductor_materials: {bulk: SiGe30} # 可选
    gate_semiconductors: {gate: bulk}      # 可选
    doping:                                # 每 silicon region 一条；缺省 lateral_sd
      bulk: {profile: lateral_sd}          # 复用现有解析剖面（junction 位置由
                                           #   device.l_sd/l_gate/junction_lambda 给）
      # 或 {profile: uniform, donors_cm3: 1e15, acceptors_cm3: 0}
      # 或 {profile: expression, donors: "<devsim 表达式>", acceptors: "..."}
```

**改动**：

- `geometry/params.py`：`DeviceParams` 增加 `external: dict | None = None`
  字段 + 校验（structure=="external" 时必填 mesh_file/dimension/regions/
  contacts，其余 structure 时必须为 None）。
- `geometry/base.py`：`MeshLayout` 增加 `doping_specs: dict`（region ->
  spec dict，默认空 = 现行为）。
- **新增 `geometry/external.py`**：`ExternalMeshBuilder(GeometryBuilder)`，
  `build(msh_path)` 做三件事：解析用户 `.msh` 的 `$PhysicalNames` 段
  （纯文本，几行代码），校验映射里每个名字都存在（报错时列出文件里实际
  可用的 group 名）；把用户网格复制到输出目录的 `msh_path`（保持 Runner
  "输出目录自包含"的约定）；组装并返回 `MeshLayout`（含 doping_specs）。
  注册进 `geometry/__init__.py::BUILDERS["external"]` —— Runner/CLI 全部
  调用点零改动。
- **doping 分派**：`physics/doping.py` 增加
  `create_doping_from_spec(device, region, params, polarity, spec)`：
  lateral_sd → 现有 `create_doping`；uniform/expression → 直接
  `CreateNodeModel`（Donors/Acceptors/NetDoping/TotalDoping +
  `edge_from_node_model`，与现有模型集合一致）。调用点两个：
  `solve/initial.py:77`（`layout.doping_specs.get(region)` 优先）与
  `workflow/cli.py` structure 命令的同型循环。
- `workflow/config.py`：mesh_file 相对路径在 `load_config` 时解析为绝对
  （相对配置文件目录）；`gui/config_form.py` CHOICES 的 structure 加
  "external"。

### ② sweep 的 CSV 设计点导入

**CLI**：`cfet-tcad sweep base.yaml --points doe.csv -j 4`（`--points` 与
`-p` 互斥、二选一）。CSV 首行为点分路径列名，每行一个设计点：

```csv
device.l_gate_nm,physics.mobility_model
12,doping_vsat
15,lombardi_vsat
```

**改动**（都在 `workflow/sweep.py` + `workflow/cli.py`）：

- 从 `parse_param_spec` 提出值强转函数 `_coerce(str) -> int|float|str`
  （两处共用）。
- 新函数 `load_points_csv(path) -> list[dict]`：只把首段是已知配置节
  （device/mesh/physics/simulation/output/extract）的列当参数,其余列
  忽略并打印提示——这样用户可把导出的 `sweep_summary.csv` 改一改直接
  回灌（fom/status 列自动跳过），导入导出闭环。
- `run_sweep(...)` 增加 `points: list[dict] | None` 参数,给了 points 就
  直接用（tag/汇总/趋势图路径全复用；趋势图轴 = 第一个全数值列）。
- **GUI**：`main_window.py::SweepDialog` 加 "Import CSV..." 按钮——读入
  points 后转写为每列一行的 `path=v1,v2,...` 并自动勾选 zip（CSV 行
  = zip 语义,零新机制）。

### ③ STL / OBJ 几何导出

**改动**：

- `io/render3d.py` 新增两个函数：
  - `export_surface(vtk_dir, path, prefix=None)`：`load_snapshot` →
    每 region `extract_surface()` → `pyvista.merge` → `save(path)`。
    扩展名决定格式（`.stl` / `.ply` / `.vtp`），**无需 GL**，任何环境可用；
  - `export_obj(vtk_dir, path, prefix=None)`：off-screen Plotter +
    现有 `add_device`（材质配色）→ `plotter.export_obj`（带 `.mtl` 颜色）。
    需要 GL/OSMesa（与截图同条件,CI 走 xvfb）。
- **CLI**：`structure` 子命令加 `--stl PATH` 与 `--obj PATH` 选项（与
  现有 `--png` 并列,同一段代码路径）。
- **GUI**：`gui/structure_view.py` 控制条加 "Export..." 按钮（QFileDialog,
  过滤器 STL/PLY/VTP/OBJ;OBJ 仅在 3D 可用（非 NO_3D）时列出,其余格式
  永远可用——用 `export_surface` 不碰 GL）。

### 文档

- README：新增 "设计导入与导出" 小节（三个功能 + 示例命令）。
- 中英用户指南（`gui/help/guide.html` / `guide_zh.html`）：Workbench 章节
  加一小段 + CSV/外部网格示例。

### 测试（加入 tests/，模式沿用现有文件）

1. `test_external_mesh.py`：用 `nanosheet_2d` builder 生成 `.msh`,再写
   structure=external 的配置映射同一批 group 名,跑 `structure` 流程断言
   region/接触齐全、NetDoping 正确;**交叉验证**:同参数 builder 路径 vs
   external 路径各跑一个 3 点 Id-Vg,电流逐点一致（延续本项目位精确
   交叉验证传统,粗网格秒级）;负例:映射写错名 → 报错信息含实际可用名。
2. `test_sweep.py` 增补:`load_points_csv` 强转/列过滤单测 +
   `sweep_summary.csv` 回灌兼容单测;`--points` 端到端 2 点 sweep(模式
   照抄 `test_sweep_two_points_end_to_end`）。
3. `test_render3d.py` 增补:`export_surface` 出 STL 断言
   `pv.read(...).n_cells > 0`（无 GL 依赖）;OBJ 测试放
   `test_offscreen_render_nonblank` 同款 fixture 下（CI xvfb 已就绪）。
4. GUI 冒烟:SweepDialog import 按钮的转写逻辑单测（不开文件对话框,
   直接调转换函数）。

### 验证

1. 全套 pytest（现 66 + 新增 ~8）绿;
2. 手动端到端:导出 nanosheet mesh → external 配置跑通 idvg;
   `sweep --points` 3 点表格跑通出 trend;`structure --stl --obj` 出文件并
   在 pyvista 里读回;
3. Linux CI 绿（Windows 打包不自动触发,按约定提示用户手动触发）。

### 风险

- 外部网格的物理正确性靠用户（结位置与 doping 剖面匹配）——文档明确
  lateral_sd 的 junction 坐标语义,并提供 uniform/expression 兜底;
- `create_gmsh_mesh` 只认 MSH 2.2 ASCII——解析 `$MeshFormat` 头,版本
  不对时直接给出 `gmsh -save_all -format msh22` 转换提示;
- OBJ 导出依赖 GL——GUI 里按 NO_3D 门控,文档注明。

**结果**：提交 `e26dec9`。外部网格位精确交叉验证通过；suite 82。

---

## 把 configs/ 示例设计文件打进两条 Windows exe 包

> 归档说明：本计划在 plan mode 中生成并经用户批准执行，完成后补充归档
> （原计划文件被后续 plan-mode 会话覆盖，从对话记录回填）。对应提交：
> `cee0109`。

### Context

用户问 "configs 目录中的设计文件打包到 exe 的 zip 中了么？"——排查确认
**没有**：spec 的 `collect_data_files("cfet_tcad")` 只收包内数据（help/
icons），configs/ 在仓库根、包外；两条工作流上传的 dist 目录里都没有。
CI 冒烟用仓库 checkout 的 configs 掩盖了缺口。后果：用户解压后 GUI 配置
浏览器为空（默认找 `cwd/configs`），11 个示例设计全都不可见。

### 改动

1. **两条工作流各加一步"复制示例配置"**（编译后、冒烟前）：
   - `.github/workflows/windows-exe.yml`：`cp -r configs dist/cfet-tcad/configs`
   - `.github/workflows/windows-nuitka.yml`：`cp -r configs build/entry_nuitka.dist/configs`
   - 选择工作流复制而非 spec datas：PyInstaller 6 会把 datas 埋进
     `_internal/`，而示例配置应该放在 exe 旁边让用户能看到、能改。
2. **冒烟改用包内 configs 防回归**：两条跑道现有的 "CLI structure
   export" 冒烟步骤把 `configs/nsheet_nfet_2d.yaml` 改成
   `./dist/cfet-tcad/configs/...`（Nuitka 同理）——不存在则直接红。
3. **GUI frozen 回退**（`src/cfet_tcad/gui/app.py::main`）：当前
   `root = argv[1] 或 cwd`；增加：frozen 且 `root/configs` 不存在时回退
   到 `Path(sys.executable).parent`（两种打包 exe 都在 dist 根，旁边就是
   configs）——双击 exe 时（cwd 可能是 system32 或任意目录）配置浏览器
   仍能列出示例。
4. **测试**（tests/test_gui.py）：新增 app 根目录选择逻辑的单测——把
   选根逻辑提为 `gui/app.py::default_project_root(argv, frozen, exe_dir)`
   纯函数以便 Linux 上直测（frozen+无 configs → exe_dir；有 argv → argv）。
5. **README** Windows 章节一句话：解压后 `configs/` 内含全部示例设计。

### 验证

1. `pytest tests/test_gui.py -q` 绿（新单测覆盖回退逻辑）；
2. 推送后提示用户手动触发两条 Windows 工作流（按既定约定不自动跑）；
   冒烟改用包内 configs，工件里缺 configs 会直接失败；
3. 工件下载解压后目录结构：`cfet-tcad.exe` 旁有 `configs/*.yaml` 11 个。

### 结果

已实现并推送（`cee0109`），全套测试绿。

---

## 修 doctor 在 Windows 上的临时目录清理失败（构建红）

> 归档说明：本计划在 plan mode 中生成并经用户批准执行，完成后补充归档
> （原计划文件被后续 plan-mode 会话覆盖，从对话记录回填）。对应提交：
> `60b1816`。

### Context

用户手动触发的 Windows EXE 构建（run 28743992681, 099c282）在新加的
"Frozen smoke - doctor self-diagnosis" 步骤失败。日志显示微型求解本身
完全收敛（平衡态+DD 都过了），但 `tempfile.TemporaryDirectory` 退出清理
时报 `PermissionError: [WinError 32] doctor.msh 正被另一进程使用`——
devsim 的 `create_gmsh_mesh` 在 Windows 上持有 .msh 句柄不放，Windows
不允许删除打开中的文件（Linux 允许，故本地/Linux CI 全绿）。doctor 把
这算作 [FAIL] → 退出码 1 → 构建红。in-progress 的 Nuitka 构建走到同一
步骤也会踩中。

### 改动

- `src/cfet_tcad/workflow/doctor.py::run_doctor.solve`：
  `tempfile.TemporaryDirectory()` →
  `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`（Py3.10+,
  CI 为 3.11）；锁住的文件留在系统临时目录由 OS 回收。

### 验证

1. `pytest tests/test_bootstrap.py -q`（含 test_doctor_reports_healthy）绿；
2. 推送后提示用户重新手动触发两条 Windows 工作流；doctor 步骤应转绿，
   随后的非 ASCII 求解冒烟与 DETACHED_PROCESS GUI 冒烟继续验证。

### 结果

已实现并推送（`60b1816`），全套测试绿。

---

## 复现论文:Fin-based vs Sheet-based CFET 对比仿真（AMAT, 3nm 节点）

### Context

用户上传 Applied Materials 的 IEEE 论文《Complementary FET Device and
Circuit Level Evaluation Using Fin-Based and Sheet-Based Configurations
Targeting 3nm Node and Beyond》,要求评估我们的程序能否做类似仿真,提取
论文器件参数,仿真并比较差异。

**论文方法**:3D-TCAD 漂移扩散（向 sub-band BTE 校准 DG/低场迁移率/
vsat 参数）,对比 fin-based CFET (FBC, 2 fin) 与 sheet-based CFET
(SBC, 2 sheet),器件级 Ion-Ioff + 电路级 31 级环振。**与我们的框架
路线完全一致**(DD + DG + 迁移率模型 + 3D CFET 堆叠)。

**论文参数表 (Fig.2)**:Gate Pitch 45nm / **Lg 15nm** / **N-P间距
30nm** / Fin 18(高)×5(宽)nm / **Nanosheet 18(宽)×5(厚)nm** / 每器件
2 sheet 或 2 fin / Vdd 0.7V / nMOS 叠在 pMOS 上 / pMOS 500MPa 压应力
（两种构型同等施加）。

**论文核心结论（对比目标）**:同有效沟道宽度下 SBC nMOS Ion **+10%**、
pMOS **−5%**（机理:SBC 沟道以 (100) 面为主 vs FBC (110) 面——电子
迁移率 (100)>(110),空穴相反）;sheet 加宽到 31nm(同底面积)后
+73%/+47%;环振频率 +2.6%/+9%。

**能力匹配**:✅ 3D CFET 堆叠(cfet_3d)、DD+DG、Ion/Ioff/SS 提取、
cfet_vtc 反相器混合仿真;⚠️ 面取向迁移率各向异性需加**标定旋钮**
(论文自己也是靠标定);❌ 应力迁移率(两构型同等,相对比较中抵消)、
BTE 校准源、寄生RC+环振瞬态(声明范围外,用 VTC 作电路级替代)。

### 改动

#### 1. 面取向迁移率标定旋钮（论文式 DD 标定的最小实现）

- `workflow/config.py::PhysicsConfig` 增加 `mobility_scale_n: float=1.0`
  / `mobility_scale_p: float=1.0`;
- `physics/mobility.py::_create_lowfield_edge_models` 接受 scale 并乘进
  mu_n_lf/mu_p_lf 表达式（doping/doping_vsat/lombardi 全链路自动生效,
  lombardi 的 CVT 组合以 mu_*_lf 为输入）;
- `solve/initial.py::setup_equilibrium` + `workflow/runner.py::setup`
  透传两个新参数;GUI 参数表单自动出现（dataclass 驱动）。

#### 2. 论文参数配置（3 个新 configs/,参数出处均注释论文 Fig.2）

- `paper_sbc_cfet_3d.yaml`:sheet 18×5、Lg15、l_sd=(45−15)/2=15、
  t_gap30、n_sheets 2、Vdd 0.7、doping_vsat+DG、(100) 基准
  scale_n/p = 1.0/1.0;
- `paper_fbc_cfet_3d.yaml`:同上但截面转 90°(sheet_width 5、t_si 18,
  近似 fin;文档注明 GAA-vs-三栅差异),(110) 面 scale_n/p = 0.75/1.40
  （文献典型 Si 面取向迁移率比,报告中说明并做敏感性讨论）;
- `paper_sbc31_cfet_3d.yaml`:SBC 加宽 31nm(同底面积对比点)。
- 未给出的参数取本仓库默认并在报告中列明假设:EOT≈1nm、S/D 1e20、
  沟道 1e15、WF_n/p 用现值(4.50/4.72,两构型相同——论文同款做法)。

#### 3. 对比分析脚本 + 报告

- `examples/paper_cfet_comparison.py`:顺序跑 3 个配置(或 `--use`
  复用已有结果目录),从 cfet_idvg.csv 以**恒 Ioff 插值**读取
  Ion@Ioff=1nA(条数不足时退化到报告各自 Ion/Ioff/SS),算 SBC vs FBC
  的 ΔIon(n/p)、宽 sheet 增益;另跑 FBC/SBC 的 `cfet_vtc` 作电路级
  替代指标(VM/增益/噪声容限);输出 `docs/paper_comparison.md`
  (对照表:论文值 vs 本程序值 vs 差异原因)+ 对比图 PNG。
- 差异预期与解释(写进报告):无应力模型(同等施加,相对值近似抵消)、
  fin 用 GAA 近似(静电略优)、迁移率取向比为文献值而非 BTE 标定、
  无寄生 RC 故不做环振。

#### 4. 测试

- `tests/test_materials.py` 或新增:mobility_scale 旋钮单测(表达式
  含 scale、默认 1.0 行为不变——与现有金标准曲线位精确一致);
- 3 个新 config 过 build_config 校验的冒烟测试;
- 全套 pytest 不回归(mobility 表达式默认路径字符串不变)。

### 验证

1. 全套 pytest 绿(默认 scale=1.0 时与既有位精确交叉验证兼容);
2. 顺序跑 3 个论文配置(每个 3D CFET 约 5-8 分钟)+ 2 个 VTC,
   生成对比表/图;核对趋势方向:SBC nMOS Ion 高于 FBC、pMOS 低于
   FBC、31nm 宽 sheet 大幅领先;
3. 把对比图和报告发给用户(SendUserFile),提交推送。

**结果**：提交 `0e41666`→`0aa300e`。四项对比方向全部与论文一致（+7.7%/−9.1%/+48.9%/+28.0% vs 论文 +10%/−5%/+73%/+47%）；后续延伸出 Fig4/8/9 风格图（`abc280b`→`37e27be`）。

---

## cfet_3d 多沟道复制:每器件多 fin(并排)/ 多 sheet(叠层)

### Context

用户对照论文 Fig.4 的 fin-based CFET 插图提问:上半 pMOS、下半 nMOS
**各有两个 fin 并排**,当前器件与渲染是否支持。现状:cfet_3d 每器件只
mesh 一个沟道体,n_sheets 仅是电流乘数;渲染端按 region 工作,builder
画出来就能渲染。论文的两种构型都要多沟道:FBC = 每器件 2 fin 横向并排
(fin pitch 26nm),SBC = 每器件 2 nanosheet 纵向叠层。

**核心设计**:gmsh 物理组可含多个不相连的体——把一个器件的所有沟道
复制体并入同一个 silicon_n/oxide_n/source_n/... 物理组,命名契约零变化
→ 加载器、物理装配、求解、runner、渲染器全部零改动;DEVSIM 对含不连通
分量的 region 求解无碍(块对角子系统)。

### 改动(要点)

1. DeviceParams:n_fins/fin_pitch_nm(横向)、n_stacked_sheets/
   sheet_pitch_nm(纵向)+ 氧化壳重叠与结构限制校验;
2. cfet_3d builder:器件循环内套 fi×si 复制循环,体/面聚合后一次性
   addPhysicalGroup;nFET 基准 y 随 pFET 叠层总高抬升;默认 1×1 路径
   与旧网格逐字节一致;
3. 论文 5 配置切真实几何(FBC 2 fin @26nm;SBC/SBC31 2 sheet @15nm
   假设 pitch),n_sheets 乘数退为 1;
4. 重跑两个 lombardi 配置重出 Fig4/8/9;
5. 测试:双沟道电流精确 = 2×单沟道(两个复制轴)、校验负例;
6. 额外评估(应用户要求):meshwell 不引入(OCC 1e-7 公差 vs nm-in-cm、
   非结构网格破坏位精确基线);ParaView 已天然支持,交付
   examples/paraview_macro_fig8.py 宏 + README 查看指南;pvpython 不
   引入(2GB 独立解释器 vs 进程内 PyVista,唯一差距 OSPRay 光追由用户
   本地 ParaView 免费获得)。

### 结果

实现落地于提交 `21076d9`:默认路径网格 MD5 与旧 builder 逐字节一致;
双 fin 与双叠层电流均精确 = 2×单沟道(rel <1e-6),不连通 region 求解
正确性同时得证;测试套 94。真实 2-fin/2-sheet 几何的 Fig4/8/9 重渲染
随 lombardi 重跑完成后交付(见 PROJECT_DEV_PLAN 待办)。

---

## GUI 实验表:running 进度百分比 + 单实验停止/删除

### Context

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

### 改动

#### 1. runner 发进度(`workflow/runner.py`)

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

#### 2. RunQueue 重构 + 单实验停止(`gui/run_queue.py`)

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

#### 3. 表格模型(`gui/experiment_table.py`)

- `Experiment` 增 `progress: float | None = None`;
- `STATUS_COLORS` 增 `"stopped": QColor("#aab7c4")`(灰蓝);
- Status 单元格显示:running 且有进度时 → `"running 45%"`;
- 新 `remove(row)`(beginRemoveRows/endRemoveRows)与 `row_of(exp)`。

#### 4. 右键菜单(`gui/main_window.py`)

Experiments 表 `setContextMenuPolicy(Qt.CustomContextMenu)`,菜单项:
- **Stop** —— running/queued 时可用,调 `queue.stop(exp)`;
- **Remove from list** —— 非 running 时可用,调 `model.remove(row)`
  (只移除表格行,**不删磁盘结果**,菜单文字明示);
- **Open results folder** —— `QDesktopServices.openUrl`(顺手的小增强)。
工具栏 Stop(全停)保留。

#### 5. 测试(tests/test_gui.py + tests/test_solve_smoke.py 增补)

1. `parse_progress_line` 命中/不命中;
2. Status 单元格文本:running+progress=0.45 → "running 45%";
3. `model.remove` 中间行后顺序/计数正确;Experiment 可哈希;
4. `stop` 对 queued 实验 → "stopped" 且不再被调度(`_maybe_start` 后
   仍 stopped);
5. (slow)tiny idvg 经 `run_config` 跑完,capsys 里 `@@PROGRESS` 行数
   == 总点数+1 且末行 done==total。

#### 6. 文档与归档

- 中英用户指南 Experiments 小节补一句(进度百分比、右键停止/移除);
- 按 CLAUDE.md 约定归档:`docs/dev_plan_gui_progress_stop_delete.md` +
  DEV_PLANS_ARCHIVE.md 追加 + PROJECT_DEV_PLAN 索引/状态更新。

### 验证

1. 全套 pytest 绿(新增 ~5 测试);
2. 手动:offscreen 起 GUI 逻辑冒烟已由单测覆盖;真实交互验证留给用户
   在 Windows exe 上做(改动后提醒手动触发打包);
3. Linux CI 绿。

### 风险

- 子进程 stdout 缓冲吞百分比 → 已用 flush=True 针对;若 PyInstaller
  Windows 下仍有缓冲差异,`_ensure_std_streams`/`-u` 兜底可加(实测再说);
- 行号漂移类回归 → 全部行号现算 + 以对象为键,配删除中间行的单测。

### 结果

已实现并推送。runner 每测一个偏压点打印 `@@PROGRESS k/n`(flush),
RunQueue 解析后在 Status 单元格显示 "running 45%",进度行不进日志;
进程表改以 Experiment 对象身份为键(`@dataclass(eq=False)`),右键菜单
提供 Stop / Remove from list(保留磁盘文件)/ Open results folder,
新增 "stopped" 状态(灰蓝)。测试 +5(解析/显示/移除/身份/停止调度
+ slow 进度覆盖测试)。
