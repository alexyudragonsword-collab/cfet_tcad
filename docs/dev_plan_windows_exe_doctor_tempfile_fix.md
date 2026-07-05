# 修 doctor 在 Windows 上的临时目录清理失败（构建红）

> 归档说明：本计划在 plan mode 中生成并经用户批准执行，完成后补充归档
> （原计划文件被后续 plan-mode 会话覆盖，从对话记录回填）。对应提交：
> `60b1816`。

## Context

用户手动触发的 Windows EXE 构建（run 28743992681, 099c282）在新加的
"Frozen smoke - doctor self-diagnosis" 步骤失败。日志显示微型求解本身
完全收敛（平衡态+DD 都过了），但 `tempfile.TemporaryDirectory` 退出清理
时报 `PermissionError: [WinError 32] doctor.msh 正被另一进程使用`——
devsim 的 `create_gmsh_mesh` 在 Windows 上持有 .msh 句柄不放，Windows
不允许删除打开中的文件（Linux 允许，故本地/Linux CI 全绿）。doctor 把
这算作 [FAIL] → 退出码 1 → 构建红。in-progress 的 Nuitka 构建走到同一
步骤也会踩中。

## 改动

- `src/cfet_tcad/workflow/doctor.py::run_doctor.solve`：
  `tempfile.TemporaryDirectory()` →
  `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`（Py3.10+,
  CI 为 3.11）；锁住的文件留在系统临时目录由 OS 回收。

## 验证

1. `pytest tests/test_bootstrap.py -q`（含 test_doctor_reports_healthy）绿；
2. 推送后提示用户重新手动触发两条 Windows 工作流；doctor 步骤应转绿，
   随后的非 ASCII 求解冒烟与 DETACHED_PROCESS GUI 冒烟继续验证。

## 结果

已实现并推送（`60b1816`），全套测试绿。
