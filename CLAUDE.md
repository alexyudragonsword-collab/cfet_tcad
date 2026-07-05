# CLAUDE.md

Guidance for Claude Code sessions working in this repository.

## Plan-mode archival (standing instruction)

Whenever a `/plan`-mode session produces a detailed plan and the user
approves it (`ExitPlanMode`), **archive the plan** after the work is
done, in addition to executing it:

1. Copy the approved plan's full content into
   `docs/dev_plan_<short-slug>.md` (slug describes the feature/fix,
   e.g. `dev_plan_paper_cfet_comparison.md`). Append a short "结果"
   section noting the outcome and the commit(s) it landed in.
2. Update `docs/PROJECT_DEV_PLAN.md` — the single rolling project-wide
   plan/status doc:
   - Add or update the relevant phase/milestone bullet.
   - Add a row to the "Plan-mode 计划归档索引" table pointing at the
     new archive file.
   - Refresh the stats in "当前状态一览" (line/test/config counts,
     commit count) if they've drifted meaningfully.
3. Commit both files (the archive + the updated project plan) together
   with the feature work, or as an immediate follow-up commit if the
   plan file only exists after implementation finishes.

This applies **only** to work that actually went through the
plan-mode/`ExitPlanMode` workflow — quick fixes, direct Q&A, and
one-off debugging done without a formal plan don't need an archive
entry (though they're still worth a line in `PROJECT_DEV_PLAN.md`'s
phase history if they're substantial).

Do not wait to be asked again each time — this is a durable convention
for every future session in this repo.

## Other standing conventions

- Windows packaging workflows (`windows-exe.yml`, `windows-nuitka.yml`)
  are **manual-trigger only** (`workflow_dispatch` or a `v*` tag) —
  never add branch-push triggers back without the user explicitly
  asking. After pushing changes relevant to the Windows build, remind
  the user to trigger the workflows manually from the Actions tab.
- Commit messages end with a `Co-Authored-By` and `Claude-Session`
  trailer (see recent `git log` for the exact format); never include
  the specific model identifier/name anywhere in committed content.
- Develop on the branch named in the session's task description
  (currently `claude/cfet-tcad-simulation-zh2kfo`); `main` is only
  touched with explicit user approval.
