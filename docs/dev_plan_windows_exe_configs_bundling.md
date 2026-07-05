# 把 configs/ 示例设计文件打进两条 Windows exe 包

> 归档说明：本计划在 plan mode 中生成并经用户批准执行，完成后补充归档
> （原计划文件被后续 plan-mode 会话覆盖，从对话记录回填）。对应提交：
> `cee0109`。

## Context

用户问 "configs 目录中的设计文件打包到 exe 的 zip 中了么？"——排查确认
**没有**：spec 的 `collect_data_files("cfet_tcad")` 只收包内数据（help/
icons），configs/ 在仓库根、包外；两条工作流上传的 dist 目录里都没有。
CI 冒烟用仓库 checkout 的 configs 掩盖了缺口。后果：用户解压后 GUI 配置
浏览器为空（默认找 `cwd/configs`），11 个示例设计全都不可见。

## 改动

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

## 验证

1. `pytest tests/test_gui.py -q` 绿（新单测覆盖回退逻辑）；
2. 推送后提示用户手动触发两条 Windows 工作流（按既定约定不自动跑）；
   冒烟改用包内 configs，工件里缺 configs 会直接失败；
3. 工件下载解压后目录结构：`cfet-tcad.exe` 旁有 `configs/*.yaml` 11 个。

## 结果

已实现并推送（`cee0109`），全套测试绿。
