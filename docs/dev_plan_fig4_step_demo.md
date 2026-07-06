# 论文 Fig4 风格 CFET 的 .step 示例:生成 + 经 import-step 导入仿真

## Context

用户问:能否生成类似论文 Fig4 的 3D 结构(FBC CFET:下 nMOS 双 fin、
上 pMOS 双 fin),**以 .step 格式**,可被本程序导入。这正好为刚落地的
STEP 导入功能提供一个开箱即用的官方示例(dogfood):CAD → import-step
→ external → cfet_idvg 全链路。

已核对的契约:

- `runner.py:46` gates = 挂在 Oxide 区域的接触;cfet_idvg 硬性要求
  接触名 `source_n/drain_n/source_p/drain_p`(`runner.py:231-251`);
- external 掺杂 `lateral_sd`(`physics/doping.py`)结位置取
  `device.l_sd/l_gate` ——几何沿 x 按 [l_sd | l_gate | l_sd] 排布即可
  复用解析剖面;`silicon_polarity`/`gate_workfunctions` 均由 external
  段支持;
- gmsh 写出的 STEP 只有通用 product 标签 → 示例 spec 用 **bbox 选择器**
  (这也是教学上最稳的示范)。

**转换器需补一个物理正确性过滤**:接触 bbox 若覆盖整个氧化壳,会把
硅-氧界面面一起选中(界面面同属两区域边界)。接触本就应落在器件
**外表面**——在 `convert_step` 的接触解析中排除与任何其他区域共享的
面(几行改动),gate 用「整壳 bbox」就能干净选中全部外表面。

## 改动

### 1. 转换器接触过滤(`src/cfet_tcad/geometry/step_import.py`)

`convert_step` 接触解析处:预先算好每个 region 的边界面集合,接触
候选面 = bbox 命中 ∩ owner 边界 **− 其他 region 的边界面**(界面面
排除)。docstring 补一句说明。现有报错路径不变。

### 2. 生成脚本(新 `examples/make_paper_fig4_step.py`)

用 gmsh OCC(nm 为 CAD 单位)拼 FBC 双 fin CFET,尺寸取
`configs/paper_fbc_cfet_3d.yaml`(论文 Fig.2):fin 5(W)×18(H)nm、
Lg 15、l_sd 15(硅体全长 45)、fin pitch 26、t_ox ~2、N-P 间距 30:

- 每器件 2 个硅 fin 长条(S/D+沟道连续体)+ 2 个只包住栅段的氧化壳
  (四面环包,同参数化 builder 的近似);nFET 在下、pFET 在上;
- 共 8 个体;写 `configs/paper_fbc_cfet_demo.step`(提交入库,文本
  格式几十 KB,exe 打包自动带上);
- 同时写映射 spec `configs/paper_fbc_cfet_demo_import.yaml`
  (unit_cm 1e-7;4 个 region:silicon_n/oxide_n/silicon_p/oxide_p,
  bbox 选择;6 个接触:source/drain 取硅体两端面、gate_n/gate_p 取
  整壳 bbox;interfaces:si_ox_n/si_ox_p)——GUI 里右键 .step →
  Convert 时用户能看到一份"抄得走"的真实 spec;
- 脚本支持 `--convert` 选项:生成后当场跑转换 + 出图(开发自查用)。

### 3. 配套可跑配置(`configs/paper_fbc_cfet_demo_run.yaml`,提交)

手工润色的 external 运行配置(starter 太通用,CFET 需要极性/功函数):
`mesh_file: paper_fbc_cfet_demo.msh`(转换后就位,config 目录相对
解析);regions/contacts/interfaces 同 spec;
`silicon_polarity: {silicon_n: n, silicon_p: p}`;
`gate_workfunctions` 取 paper_fbc 配置的 n/p 值;两硅区
`doping: {profile: lateral_sd}`;`simulation: cfet_idvg`(vdd 0.7,
参数对齐 paper_fbc);文件头注释写明「先对 .step 右键 Convert 生成
.msh,再 Add 本配置」。

### 4. 测试(tests/test_step_import.py 增补)

- 生成器可导入调用:在 tmp 下生成 STEP + spec,`convert_step` 走通,
  `read_msh_physical_names` 含全部 10 个组(4 region + 6 接触/界面);
- **接触不含界面面**:gate 物理组的面数 > 0,且断言 gate 面集合与
  si_ox 界面面集合不相交(gmsh 侧在 convert 后重新打开 .msh 数一次,
  或转换器 summary 里带出面数并单测集合逻辑);
- 现有 STEP 测试不受影响(接触过滤只影响与界面共享面的场景)。

### 5. 手动验证 + 交付

- `import-step` 转换 shipped spec → `cfet-tcad run` 跑
  paper_fbc_cfet_demo_run.yaml(cfet_idvg,分钟级,后台跑);
- 用 pyvista 对导入结构出一张 Fig4 风格结构图(双 fin 并排、上下
  堆叠,复用 examples/paper_structure_mobility_figures.py 的
  `_clip_open`/配色套路,一次性脚本即可不入库),连同 GUI 转换对话框
  打开该 .step 的截图发用户;
- 中英指南 STEP 小节补一句「configs/ 内置 paper_fbc_cfet_demo.step
  示例」;
- 按 CLAUDE.md 归档(dev_plan_fig4_step_demo.md + 两总档 + 索引);
- 推送后提醒 Windows 打包待手动触发(demo 文件随 configs 打包)。

## 验证

1. 全套 pytest 绿(新增 ~2 测试);
2. 转换后的 starter/润色配置真实求解收敛,cfet_idvg 曲线/FOM 正常;
3. 结构图肉眼核对:与论文 Fig4 截图同构(每器件两个并排 fin,
   栅氧化壳只包沟道段)。

## 风险

- OCC 在 nm-CAD 单位下拼 8 个盒子无容差问题(度量 ~5-45,远离 1e-7);
- 双 fin/双区域不连通 → 已有块对角求解精确性证明,无新风险;
- cfet_idvg 对 external 结构首次使用 —— 接触命名契约已核对,若
  求解暴露其它隐含假设(如接触面朝向),在示例配置层面解决,不动
  求解器。

## 结果

按计划落地(见本次提交):`examples/make_paper_fig4_step.py` 生成
论文尺寸的双 fin FBC CFET(8 个体:每器件 2 fin + 2 栅氧化壳,nm 为
CAD 单位),交付三件套入库:`configs/paper_fbc_cfet_demo.step`
(182KB)、映射 spec(bbox 选择器,gate 用整壳 bbox)、可跑的
`paper_fbc_cfet_demo_run.yaml`(lateral_sd 掺杂对齐几何、双极性、
paper 功函数,cfet_idvg @ Vdd 0.7)。转换器补上接触**外表面过滤**
(排除与其他 region 共享的界面面)——gate 整壳 bbox 因此安全,
且物理上普适正确。转换结果 6436 节点、4 区域各 2 体;测试增
生成器→转换→gate/界面面不相交 + shipped spec 与生成器同步校验;
真实 cfet_idvg 求解收敛(结果见提交说明)。
