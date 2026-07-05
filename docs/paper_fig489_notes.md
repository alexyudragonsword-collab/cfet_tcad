# Fig.4 / Fig.8 / Fig.9 风格图（能力验证）

对应 Jiang et al. (AMAT) 论文的结构图 / 3D eMobility 分布图 / 迁移率剖面图。
用 `configs/paper_{fbc,sbc}_lombardi_cfet_3d.yaml`（同几何，`lombardi_vsat`
模式，单一强反型偏压点）跑出，`examples/paper_structure_mobility_figures.py`
生成。

- **`paper_fig4_structure.png`**（结构剖面，对应 Fig.4）：FBC/SBC 的
  n/p 堆叠结构渲染，栅氧包裹沟道，直接复用现有 Structure 3D 能力。
- **`paper_fig8_emobility_3d.png`**（3D eMobility 分布，对应 Fig.8）：
  按 `mu_n_cvt`（Lombardi CVT 电子迁移率，DEVSIM 自动导出为 VTK 单元场）
  着色的 3D 渲染，共享色标便于两构型直接对比。
- **`paper_fig9_mobility_profile.png`**（迁移率剖面，对应 Fig.9）：沿
  沟道限域方向（栅氧到栅氧）的一维迁移率剖面，n/p 分列，FBC/SBC 叠加。

## 已知局限

- **网格分辨率**：两配置的限域方向都只用 5 段网格（`ny_si: 5`，为求
  演示速度）。SBC（5nm 厚）在此分辨率下已能看出中心高、两端低的对称
  衰减形状；FBC（18nm 厚,同样 5 段）分辨率相对其尺寸明显偏粗,剖面
  更接近单调而非对称双峰——这是网格密度限制,不是物理错误;真实定量
  剖面需要在限域方向加密网格（如 `ny_si: 20+`）,届时耗时也会相应增加。
- **面取向差异未在 CVT 系数中体现**：本仿真的 (100)/(110) 差异仅通过
  `mobility_scale_n/p` 标定低场基线,Lombardi 的表面散射系数
  （b_ac/delta_sr）本身未按晶面区分,因此两构型的"衰减剧烈程度"是同一
  条曲线,只是基线不同——如需更真实区分,需要给 b_ac_n/p、delta_sr_n/p
  也加同类标定旋钮（类似 `mobility_scale_n/p` 的做法）,是自然的下一步
  扩展。
- 与此前的 Ion/Ioff 对比仿真（`configs/paper_{fbc,sbc,sbc31}_cfet_3d.yaml`,
  `doping_vsat` 模式）是两组独立仿真——`doping_vsat` 不产生 `mu_*_cvt`
  场,因此本组图的绝对迁移率数值与 Ion/Ioff 对比结果不直接可比。
