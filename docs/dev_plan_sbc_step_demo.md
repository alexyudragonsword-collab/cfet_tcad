# 双 sheet SBC CFET 的 .step 导入示例(对齐已交付的 FBC demo)

## Context

用户要 SBC(Sheet-Based CFET)版本的 .step 导入示例,与刚交付的
FBC demo(commit `bf9ca15`)配对。SBC 与 FBC 的唯一区别是沟道横截面
与复制轴:

- FBC:fin 5(z 宽)×18(y 高),**2 个 fin 沿 z 并排**,fin_pitch 26;
- SBC:sheet 18(z 宽)×5(y 厚),**2 个 sheet 沿 y 叠层**,
  sheet_pitch 15(取自 `configs/paper_sbc_cfet_3d.yaml`)。

区域/接触/界面命名、cfet_idvg 契约、lateral_sd 掺杂(沿 x,与叠层
无关)全部相同。转换器上一轮已具备所需能力(接触仅取外表面 +
bbox 多盒并集),**无需改转换器**——纯新增示例。

FBC demo 已验证通过,**不动它**(避免重跑/重新出图),SBC 走并行的
独立生成脚本。

## 改动

### 1. 生成脚本(新 `examples/make_paper_sbc_step.py`)

镜像 `examples/make_paper_fig4_step.py` 的结构,改为 SBC 几何:

- 常量:`SHEET_W=18`(z)、`SHEET_H=5`(y)、`SHEET_PITCH=15`、
  `N_SHEETS=2`,`L_SD=L_GATE=15`、`T_OX=1`、`NP_SPACE=30`;
  设备 y 高 = `(N_SHEETS-1)*SHEET_PITCH + SHEET_H = 20`,
  `Y_P = 20 + NP_SPACE`(pMOS 叠层起点);
- `build_step`:每个器件(y 基点 0 / Y_P)内 `for k in range(N_SHEETS)`
  沿 **y** 放第 k 个 sheet(`y = y_base + k*SHEET_PITCH`,z 固定 0),
  硅长条 + 只包栅段的氧化壳(与 FBC 同样 outer-cut-hole);
- `import_spec`:bbox 选择器;gate 金属仍取壳的四个侧向外表面,但
  轴向翻转——**z 侧两平面跨全部 sheet(沿 y 展开)**,**每 sheet 各
  一对 y 顶/底平面薄板**(FBC 是反过来的)。叠层间隙里的内表面(下壳
  顶面 / 上壳底面)由 per-sheet y 板选中,是外表面、被 exterior filter
  保留,物理上正是栅金属填入叠层间隙;
- `main`:`--convert` 自检;产出
  `configs/paper_sbc_cfet_demo.step` + `_import.yaml`。

### 2. 运行配置(`configs/paper_sbc_cfet_demo_run.yaml`,提交)

近乎 FBC 运行配置的副本(区域/接触/界面名相同),差异:
`name: paper_sbc_step_demo`;`mesh_file: paper_sbc_cfet_demo.msh`;
`mobility_scale_n/p: 1.0/1.0`((100)sheet 参考,对齐 paper_sbc);
`output.directory` 改名;文件头注释说明「先 Convert .step 生成 .msh,
再 Add/Run」。掺杂/极性/功函数/vg 窗口([0,0.7] step 0.05,同 FBC
的收敛取舍)与 FBC demo 一致。

### 3. 测试(`tests/test_step_import.py` 增补)

新增 `test_sbc_demo_generator_converts_cleanly`,镜像现有 FBC demo 测试:
生成器→spec→convert;断言 4 区域各 2 体、10+ 物理组齐全、
`gate_{n,p}` 面集合与 `si_ox_{n,p}` 不相交(exterior filter)、shipped
`paper_sbc_cfet_demo_import.yaml` 与生成器同步。FBC 测试不动。

### 4. 文档 / 归档

- 中英指南 STEP 小节:把「内置 paper_fbc 示例」扩为「FBC 与 SBC 两个
  示例」;
- 按 CLAUDE.md 归档:`docs/dev_plan_sbc_step_demo.md`
  + DEV_PLANS_ARCHIVE.md 追加 + PROJECT_DEV_PLAN 索引/状态刷新
  (示例配置计数、测试数、提交号);
- 推送后提醒:Windows 打包待手动触发(demo 随 configs 打包)。

## 验证

1. 全套 pytest 绿(新增 1 测试);
2. `import-step` 转换 shipped spec → `cfet-tcad run`
   paper_sbc_cfet_demo_run.yaml(cfet_idvg,后台跑到收敛,出 FOM);
3. pyvista 出 Fig8 风格结构图(2 个叠层 sheet、上下器件),复用
   `scratchpad/render_step_demo.py` 套路;连同转换对话框截图发用户;
4. 结构肉眼核对:与论文 SBC 同构(每器件两片垂直叠层,栅氧壳只包
   沟道段)。

## 风险

- 5nm sheet 厚度网格偏粗 → 与 FBC 的 5nm fin 宽同量级,已知可收敛;
  必要时对 silicon 区加 `mesh_size_per_region`;
- 叠层间隙栅金属内表面选取 → 已确认为外表面、exterior filter 保留;
- Vg<0 收敛困难(非结构化 demo 网格)→ 沿用 [0,Vdd] 窗口,配置注释
  说明;结构化的 `paper_sbc_cfet_3d.yaml` 不受此限。

## 结果

按计划落地(见本次提交):`examples/make_paper_sbc_step.py` 生成
论文尺寸的双 sheet SBC CFET(8 个体:每器件 2 个 18×5nm 叠层 sheet
+ 2 个栅氧化壳,沿 y 叠层,pitch 15nm),交付三件套入库:
`configs/paper_sbc_cfet_demo.step` + 映射 spec(bbox 选择器,gate 板
按 y↔z 翻转以适配叠层)+ 可跑的 `paper_sbc_cfet_demo_run.yaml`
(mobility_scale 1.0/1.0 对齐 paper_sbc)。转换器**未改动**——
上一轮(FBC demo)加的接触外表面过滤 + bbox 多盒并集已足够。
转换结果 15780 节点、4 区域各 2 体;测试增
`test_sbc_demo_generator_converts_cleanly`(镜像 FBC demo 测试:
gate/界面面不相交 + shipped spec 同步)。真实 cfet_idvg 求解收敛
(结果见提交说明)。
