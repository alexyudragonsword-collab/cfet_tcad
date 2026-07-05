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

# 只生成网格
cfet-tcad mesh configs/nsheet_nfet_2d.yaml
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

两者均输出 MSH 2.2 ASCII（DEVSIM 唯一支持的 gmsh 格式）。

**输运**：Poisson + 电子/空穴连续性（Scharfetter-Gummel 离散化）、
SRH 复合、迁移率三档可选（`const` / `doping` / `doping_vsat`）：
Caughey-Thomas 掺杂依赖低场迁移率 + Caughey-Thomas 速度饱和。
迁移率表达式内联进 SG 电流公式，利用 DEVSIM 的模型感知符号求导
（`diff()`）获得含场依赖项的精确 Newton 雅可比。

**求解**：非线性 Poisson（电中性初值）→ 提升为耦合 DD → 自适应偏压
斜坡（失败步长减半）。默认开启 128 位扩展精度求解选项。

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
- **Phase 2**：3D 单纳米片 GAA ✔；待做：density-gradient 量子修正
  （在 `physics/equations.py` 载流子模型上挂广义电位）、Lombardi
  垂直场迁移率退化（需 element 级场重构）
- **Phase 3**：完整 CFET 堆叠（nFET-on-pFET，共栅，双器件同时求解）、
  寄生分析、参数扫描并行化

## 开发注意事项

- DEVSIM 表达式解析器中一元负号优先级高于 `^`：`-a^2 == (+a)^2`，
  指数必须整体加括号（见 `physics/doping.py`）。
- `devsim.reset_devsim()` 会清掉 UMFPACK direct solver 注册，
  使用 `cfet_tcad.reset()` 代替（tests/conftest.py 依赖此行为）。
- 运行测试：`pytest`（约 15 秒，含两个粗网格平衡态求解冒烟测试）。
