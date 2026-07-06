# STEP(.step)3D 模型导入:CAD → 网格 → external 仿真流程

## Context

用户问「当前程序是否能支持 .step 格式的 3D 模型输入?」——目前不支持:
设计导入只认带物理组的 gmsh **.msh(MSH 2.2 ASCII)**(`structure:
external`),而 STEP 是 CAD B-rep 几何,没有网格、没有物理组、没有
TCAD 语义(材料/接触/掺杂)。

**可行性已验证**(本环境 gmsh 4.15.2):OCC 内核在位,STEP 写/读往返
成功,`gmsh.model.getEntityName` 能读出 CAD 零件标签,
`gmsh.model.mesh.affineTransform` 在位(单位缩放用)。

方案:新增 **STEP → MSH 转换器**,产物直接进现有 `structure: external`
流程——物理/求解侧零改动。已确认交付形态:**CLI 子命令 + GUI 集成**;
体命名不确定 → **名称/体编号/包围盒三种选择器都支持**,转换器先打印
全部体的对照表。

**关键技术约束**(前期 meshwell 评估的教训):OCC 几何容差 ~1e-7 与
cm 制纳米尺寸(10nm = 1e-6 cm)相撞。因此**在 CAD 原生坐标里完成导入
与划网格**,网格生成后用 `gmsh.model.mesh.affineTransform` 把节点坐标
缩放到 cm(纯网格变换,不经过 OCC)。缩放系数来自 spec 的必填字段
`unit_cm`(1 个 CAD 单位 = 多少 cm;如 CAD 按 nm 画则 1.0e-7)。

## 改动

### 1. 转换器核心(新 `src/cfet_tcad/geometry/step_import.py`)

映射 spec(YAML,`step_file` 相对 spec 文件目录解析):

```yaml
step_file: device.step
unit_cm: 1.0e-7            # 必填:1 CAD 单位 = 多少 cm
mesh_size: 2.0             # 特征长度,CAD 单位
mesh_size_per_region: {gox: 0.5}     # 可选
regions:                   # 每个体必须被且仅被一个 region 认领
  bulk:  {select: {label: ".*silicon.*"}, material: Silicon}
  gox:   {select: {volume: 2},            material: Oxide}
  metal: {select: {bbox: [x0,y0,z0, x1,y1,z1]}, material: Oxide}
contacts:                  # 面选择器(bbox)+ 所属 region
  source: {select: {bbox: [...]}, region: bulk}
  gate:   {select: {bbox: [...]}, region: gox}
interfaces:                # region 对 → 自动找共享面
  si_ox: [bulk, gox]
```

核心函数:

- `discover_step(step_path) -> list[VolumeInfo]`:importShapes +
  synchronize,枚举 (tag, label, bbox)——CLI `--list` 与 GUI 模板都用;
- `convert_step(spec: dict, spec_dir: Path, out_msh: Path) -> summary`:
  1. `occ.importShapes` → **`occ.fragment`** 全体积布尔碎片化(多体
     STEP 装配通常不共形,fragment 产生共享面才能出共形网格);用
     fragment 的输入→子体映射把父体 label 传给子体;
  2. 解析三种选择器(label 正则 / volume tag / bbox 用
     `getEntitiesInBoundingBox` + 相对容差),每个体恰被认领一次,
     否则报错并列出未认领/重复认领的体与全部对照表;
  3. `addPhysicalGroup(3, ...)` 按 region;contacts 面选择器解析
     (非空校验)→ `addPhysicalGroup(2, ...)`;interfaces = 两 region
     体的边界面交集 → `addPhysicalGroup(2, ...)`;
  4. 网格尺寸:`mesh.setSize`(0 维实体)全局 + 按 region 覆盖;
     `generate(3)`;
  5. `mesh.affineTransform([s,0,0,0, 0,s,0,0, 0,0,s,0])`,s=unit_cm;
  6. `Mesh.MshFileVersion=2.2` 写出(默认只存物理实体,恰好强制
     "全部认领"的约定);
- `starter_external_config(spec, out_msh) -> dict`:生成可跑的
  `structure: external` 配置骨架(regions 材料、contacts、interfaces
  照抄;doping/workfunction 留模板注释),写 `<out_msh>.yaml`。

gmsh 生命周期沿用现有 builder 的 initialize/finalize 约定(参照
`geometry/base.py` 的用法)。

### 2. CLI(`workflow/cli.py`)

```
cfet-tcad import-step <spec.yaml> [-o out.msh] [--list]
```

- `--list`:只做 discovery,打印体对照表(tag / label / bbox),
  spec 里没写 regions 也能跑——用户先看名字再写映射;
- 正常模式:转换 + 打印 summary + 生成 starter YAML 路径提示。

### 3. GUI 集成(`gui/main_window.py` + 新 `gui/step_dialog.py`)

- `populate_configs` 的 glob 扩为 `*.yaml` + `*.step`/`*.stp`
  (列表项直接显示文件名,.step 不参与 Add/Edit 的 yaml 语义);
- .step 条目的双击与右键(菜单变为 **Convert to mesh... / List
  volumes**)→ `StepConvertDialog`:
  - 打开时在**本进程**跑 `discover_step`(纯 gmsh、无 GL,秒级),
    把体对照表以注释形式 + spec 模板预填进一个 QPlainTextEdit
    (文本编辑保留全部灵活性,不做表单爆炸);
  - **Convert** 按钮:spec 存为 `<step名>_import.yaml`(config 文件夹
    内),然后走 `cli_command()` 起 QProcess 跑
    `import-step ... -o <step名>.msh`(与 preview_structure 同模式,
    输出进日志面板);成功后 `populate_configs()` 刷新——starter
    YAML 出现在列表里,用户右键 Add 即可仿真;
  - List volumes 右键项:对照表直接打印到日志面板。

### 4. 测试(新 `tests/test_step_import.py` + test_gui.py 增补)

STEP fixture 在测试里用 gmsh OCC 现做(两个叠放盒子 silicon+oxide,
`gmsh.write("*.step")`),不依赖外部资产:

1. `discover_step` 返回 2 个体,label/bbox 正确;
2. 三种选择器各覆盖一次;未认领体 / bbox 选不到面 → 报错信息含对照表;
3. 输出为 MSH 2.2 且 `read_msh_physical_names` 能看到全部
   regions/contacts/interfaces(复用 `geometry/external.py` 的校验器);
4. 单位缩放:解析输出 $Nodes 坐标范围 ≈ CAD bbox × unit_cm;
5. (slow)转换 → starter 配置 → `run_config` 微型 idvg 全程跑通
   (复用 `tests/test_external_mesh.py` 的 `_external_config`/COARSE
   模式);
6. GUI:.step 出现在 config_list;StepConvertDialog 构造后模板文本
   含发现的体名。

### 5. 文档与归档

- 中英用户指南「设计导入」小节补 STEP 工作流(spec 示例、单位约定、
  三种选择器);
- 按 CLAUDE.md 约定归档:`docs/dev_plan_step_import.md` +
  DEV_PLANS_ARCHIVE.md 追加 + PROJECT_DEV_PLAN 索引/状态刷新;
- 推送后提醒:Windows exe 要拿到 import-step 需再次手动触发打包
  (gmsh pip wheel 自带 OCC,两条打包线无需改动)。

## 验证

1. 全套 pytest 绿(新增 ~7 测试;STEP fixture 自造);
2. 手动:对测试生成的 .step 跑 `cfet-tcad import-step --list` 与完整
   转换,`cfet-tcad run` 转出的 starter 配置,曲线/FOM 正常;
3. xvfb 截图 StepConvertDialog 发用户过目。

## 风险

- OCC 容差 vs 纳米尺寸 → 已定死「CAD 坐标划网格、affineTransform 缩放」
  路线,并有单位缩放单测把关;
- fragment 后 label 丢失 → 用 fragment 返回的父→子映射显式传播,
  单测覆盖(fixture 两盒子相贴,fragment 必然发生);
- 用户 STEP 单位五花八门 → `unit_cm` 必填 + 文档表(nm→1e-7,
  µm→1e-4,mm→1e-1);
- DEVSIM 只吃 MSH 2.2 → 转换器固定写 2.2,复用现有版本校验器。

## 结果

按计划落地(见本次提交):`geometry/step_import.py`(discover /
convert / starter 配置生成,OCC fragment 共形化 + label 传播 +
affineTransform 单位缩放)、CLI `import-step`(含 `--list` 发现模式,
starter 配置命名 `<mesh>_run.yaml` 避免与 spec 撞名——实测发现并修复
的碰撞 bug)、GUI 集成(.step 进文件列表,双击/右键弹
StepConvertDialog,转换走 QProcess 子进程)。一个实现层发现:gmsh 的
STEP 写出器不保留实体名(通用 product 标签),真实 CAD 才带零件名——
测试夹具据此用 label 正则匹配通用标签 + volume/bbox 选择器覆盖三种
路径。端到端验证:STEP → 转换 → external → idvg 求解收敛出 FOM。
测试 103 → 108,全绿。
