# cfet_3d 多沟道复制:每器件多 fin(并排)/ 多 sheet(叠层)

## Context

用户对照论文 Fig.4 的 fin-based CFET 插图提问:上半 pMOS、下半 nMOS
**各有两个 fin 并排**,当前器件与渲染是否支持。现状:cfet_3d 每器件只
mesh 一个沟道体,n_sheets 仅是电流乘数;渲染端按 region 工作,builder
画出来就能渲染。论文的两种构型都要多沟道:FBC = 每器件 2 fin 横向并排
(fin pitch 26nm),SBC = 每器件 2 nanosheet 纵向叠层。

**核心设计**:gmsh 物理组可含多个不相连的体——把一个器件的所有沟道
复制体并入同一个 silicon_n/oxide_n/source_n/... 物理组,命名契约零变化
→ 加载器、物理装配、求解、runner、渲染器全部零改动;DEVSIM 对含不连通
分量的 region 求解无碍(块对角子系统)。

## 改动(要点)

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

## 结果

实现落地于提交 `21076d9`:默认路径网格 MD5 与旧 builder 逐字节一致;
双 fin 与双叠层电流均精确 = 2×单沟道(rel <1e-6),不连通 region 求解
正确性同时得证;测试套 94。真实 2-fin/2-sheet 几何的 Fig4/8/9 已随
lombardi 双沟道重跑完成交付:FBC 面板显示两个并排 fin、SBC 显示两个
叠层 sheet,与论文 Fig.4 截图一致。重渲染暴露了图脚本的一个几何 bug
——原 cutaway 在器件全域 mid-z 单平面裁剪,会把整个第二个 fin 裁掉;
改为按连通体各自 mid-z 裁剪(`_clip_open`),单沟道行为不变。
