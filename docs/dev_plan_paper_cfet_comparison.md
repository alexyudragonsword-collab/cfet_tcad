# 复现论文:Fin-based vs Sheet-based CFET 对比仿真（AMAT, 3nm 节点）

## Context

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

## 改动

### 1. 面取向迁移率标定旋钮（论文式 DD 标定的最小实现）

- `workflow/config.py::PhysicsConfig` 增加 `mobility_scale_n: float=1.0`
  / `mobility_scale_p: float=1.0`;
- `physics/mobility.py::_create_lowfield_edge_models` 接受 scale 并乘进
  mu_n_lf/mu_p_lf 表达式（doping/doping_vsat/lombardi 全链路自动生效,
  lombardi 的 CVT 组合以 mu_*_lf 为输入）;
- `solve/initial.py::setup_equilibrium` + `workflow/runner.py::setup`
  透传两个新参数;GUI 参数表单自动出现（dataclass 驱动）。

### 2. 论文参数配置（3 个新 configs/,参数出处均注释论文 Fig.2）

- `paper_sbc_cfet_3d.yaml`:sheet 18×5、Lg15、l_sd=(45−15)/2=15、
  t_gap30、n_sheets 2、Vdd 0.7、doping_vsat+DG、(100) 基准
  scale_n/p = 1.0/1.0;
- `paper_fbc_cfet_3d.yaml`:同上但截面转 90°(sheet_width 5、t_si 18,
  近似 fin;文档注明 GAA-vs-三栅差异),(110) 面 scale_n/p = 0.75/1.40
  （文献典型 Si 面取向迁移率比,报告中说明并做敏感性讨论）;
- `paper_sbc31_cfet_3d.yaml`:SBC 加宽 31nm(同底面积对比点)。
- 未给出的参数取本仓库默认并在报告中列明假设:EOT≈1nm、S/D 1e20、
  沟道 1e15、WF_n/p 用现值(4.50/4.72,两构型相同——论文同款做法)。

### 3. 对比分析脚本 + 报告

- `examples/paper_cfet_comparison.py`:顺序跑 3 个配置(或 `--use`
  复用已有结果目录),从 cfet_idvg.csv 以**恒 Ioff 插值**读取
  Ion@Ioff=1nA(条数不足时退化到报告各自 Ion/Ioff/SS),算 SBC vs FBC
  的 ΔIon(n/p)、宽 sheet 增益;另跑 FBC/SBC 的 `cfet_vtc` 作电路级
  替代指标(VM/增益/噪声容限);输出 `docs/paper_comparison.md`
  (对照表:论文值 vs 本程序值 vs 差异原因)+ 对比图 PNG。
- 差异预期与解释(写进报告):无应力模型(同等施加,相对值近似抵消)、
  fin 用 GAA 近似(静电略优)、迁移率取向比为文献值而非 BTE 标定、
  无寄生 RC 故不做环振。

### 4. 测试

- `tests/test_materials.py` 或新增:mobility_scale 旋钮单测(表达式
  含 scale、默认 1.0 行为不变——与现有金标准曲线位精确一致);
- 3 个新 config 过 build_config 校验的冒烟测试;
- 全套 pytest 不回归(mobility 表达式默认路径字符串不变)。

## 验证

1. 全套 pytest 绿(默认 scale=1.0 时与既有位精确交叉验证兼容);
2. 顺序跑 3 个论文配置(每个 3D CFET 约 5-8 分钟)+ 2 个 VTC,
   生成对比表/图;核对趋势方向:SBC nMOS Ion 高于 FBC、pMOS 低于
   FBC、31nm 宽 sheet 大幅领先;
3. 把对比图和报告发给用户(SendUserFile),提交推送。
