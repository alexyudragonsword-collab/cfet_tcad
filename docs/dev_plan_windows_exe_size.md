# Windows exe 体积:先诊断,再裁剪

> 归档说明:本计划分两步落地——第一步(诊断)与第二步(裁剪)是
> 同一条思路的两个阶段,合并归档为一份。

## Context

用户反馈当前 Windows exe(PyInstaller / Nuitka 两条跑道,上传后的
压缩包均在 460–480 MB 量级)偏大,希望尽量减小。

讨论后判断头号嫌疑是 `cfet_tcad.spec` 里对 `vtkmodules` 用
`collect_all`(VTK 出了名的"裸收集会把全部子模块——含用不到的几十种
文件 IO/MPI/Cinema 等——都打进来"),其次是 MKL 全量 DLL 与 PySide6
未裁剪的 Qt 插件/翻译。但这些都是靠经验猜测,而此前这个工程已经
因为盲目裁剪 DLL 踩过两次坑(gmsh DLL 漏收集、MKL 线程层延迟加载),
两次都是构建/运行时才暴露。

所以确定的原则是:**第一步不动手术,先量出真实体积明细;有了数据
再决定裁哪一刀。**

## 第一步:构建时打印分目录体积明细

两条 workflow 都在 `upload-artifact` 之前插入一个新步骤
"Bundle size breakdown"(纯诊断,不改变构建产物,任何一步失败都不能
挂掉整个 job):

- **`windows-exe.yml`**(PyInstaller,bundle 根目录 `dist/cfet-tcad`,
  运行时收在 `_internal/`):打印 bundle 总体积、`_internal/` 下一级
  子项按体积排序、以及嫌疑包名(`vtkmodules*`、`PySide6*`、`mkl_*`/
  `libiomp5md*`、`numpy*`、`scipy*`、`matplotlib*`、`devsim*`、
  `gmsh*`、`anthropic*`/`httpx*`/`httpcore*`、`pyvista*`)的分项汇总。
- **`windows-nuitka.yml`**:插在 "Repackage into a clean,
  PyInstaller-style layout" 之后,bundle 根目录是 `build/pkg/app`
  (Nuitka standalone 是扁平目录、模块用点分名,glob 写成宽松匹配)。

两处都用 `set +e` + `2>/dev/null` + 末尾 `exit 0` +
`continue-on-error: true` 四重兜底,保证诊断步骤永远不会让构建变红。

## 第二步:依据实测数据裁剪

实测结果(PyInstaller,解包后 **1.3 GB**,zip 480 MB):

| 类别 | 体积 | 占比 |
|---|---:|---:|
| MKL(全部 `mkl_*`) | 539 M | ~41% |
| VTK(`vtk.libs` 265M + `vtkmodules` 49M) | 314 M | ~24% |
| gmsh(根目录 86M + `lib/` 86M) | 172 M | ~13% |
| PySide6 | 84 M | |
| scipy / numpy / matplotlib | 110 M | |
| devsim + pyvista | 11 M | |

据此确定"这一轮只做两刀有确凿依据的裁剪",VTK 那一刀(最大但最容易
踩坑)留待单独一轮:

### 刀一:gmsh DLL 去重(-86 MB)

打包脚本此前把同一个 `gmsh-*.dll` 同时放在 bundle 根目录和 `lib/`
下,注释写的理由是"gmsh.py probes both"。**实际读 gmsh wheel 里的
`gmsh.py` 源码确认**:它的 `possible_libpaths` 列表第一项就是
`os.path.join(moduledir, libname)`,即 gmsh.py 自身所在目录;两种
打包方式下 `moduledir` 都解析到 bundle 根目录,所以根目录那份永远
先命中,`lib/` 那份从来没被读到过——是纯副本。

同时确认 `workflow/doctor.py` 只 glob bundle 根目录与 `_internal/`,
不看 `lib/`,删掉不影响自检输出。

### 刀二:MKL 不可达 DLL(-123 MB)

pip 的 `mkl` wheel 为每种线程层、每条 VML 代码路径各带一个 DLL,但
`mkl_rt` 运行时每类只会加载其中一个:

- **线程层**:全仓库没有任何地方设置 `MKL_THREADING_LAYER`,走默认的
  `intel_thread`(首次 BLAS 调用时拉起 `libiomp5md`)。因此
  `mkl_tbb_thread`(29M)与 `mkl_sequential`(23M)不可达。
- **VML**(Intel 向量数学库,`vdExp`/`vdMul` 等):DEVSIM 调的是
  BLAS/LAPACK 与稀疏求解器,而 PyPI 上的 numpy/scipy 链接的是
  OpenBLAS 而非 MKL,没有任何路径会调进 VML 入口。因此
  `mkl_vml_*`(共 71M)不可达。

**CPU 分派变体(`def`/`mc3`/`avx2`/`avx512`/`avx10`)全部保留**——
`mkl_rt` 是在加载时按宿主 CPU 选一个,删掉任何一个都会精确地打死
需要它的那批机器,这正是"省不了多少却风险极大"的典型。

两条打包跑道各自加了断言:`mkl_rt` / `mkl_core` / `mkl_intel_thread` /
`libiomp5md` / `gmsh` 缺任何一个就让构建立刻失败,而不是产出一个
"能启动、一求解就死"的包。

## 关键文件

- `.github/workflows/windows-exe.yml`(诊断步骤 + 由 spec 承载裁剪)
- `.github/workflows/windows-nuitka.yml`(诊断步骤 + DLL 打包步骤裁剪)
- `packaging/cfet_tcad.spec`(MKL 过滤 + gmsh 单份 + 必需项断言)

## 验证

1. 诊断步骤本地 dry-run 过两轮(先修掉 `set -e` 下 `&&` 链会中断
   整步的问题,再修掉未命中 glob 打印 `0` 的噪声);
2. 用户手动触发两条 workflow,两条均 success,读出上表的真实明细;
3. 裁剪逻辑用 CI 实测的 15 个 MKL DLL 清单离线跑过一遍,确认保留
   8 个必需项、删除 7 个不可达项,省 123 MB;
4. 裁剪后需再次手动触发两条 workflow——已有的冻结冒烟(非 ASCII
   路径下的真实 DEVSIM 求解、`doctor` 自检、GUI 无窗启动、CLI
   structure 导出走 gmsh)正是这两刀的验收门。

## 结果

- 诊断步骤:提交 `79294b1`,两条 workflow 均 success
  (run 29220579855 / 29220585812),产出上表数据。
- 裁剪:见本次提交。预期解包体积 1.3 GB → 约 1.1 GB,压缩包
  480 MB → 400 MB 量级(-209 MB)。
- VTK 的 314 MB 未动,留作独立一轮(需要按 pyvista 实际用到的子模块
  做精选列表,风险显著高于这两刀)。
