# Skill Registry — Jarvis

**Generated**: 2026-04-13
**Project**: Jarvis (Python voice assistant)

## User Skills

| Skill | Trigger | Source |
|-------|---------|--------|
| go-testing | Go tests, Bubbletea TUI testing | user-global |
| angular-patterns | Angular development | user-global |
| brescopack-conventions | Brescopack projects | user-global |
| skill-creator | Creating new AI skills | user-global |
| branch-pr | PR creation workflow | user-global |
| issue-creation | Issue creation workflow | user-global |
| judgment-day | Adversarial parallel review | user-global |

## Project Conventions

| Source | Path | Scope |
|--------|------|-------|
| SPEC.md | SPEC.md | Project spec — architecture, components, tools |

## Compact Rules

### branch-pr
- Conventional commits: type(scope): description
- Branch naming: feat/, fix/, refactor/, chore/
- PR title matches commit format
- Body: Summary + Test Plan
- Link issues with `Closes #N`

### issue-creation
- Title: type(scope): description (same as commits)
- Body: what + why
- Labels: bug, feature, refactor, chore, blocked
- Skip issues for trivial changes

### judgment-day
- Two independent blind judge sub-agents review in parallel
- Synthesize findings, fix, re-judge until both pass
- Escalate after 2 iterations

## Notes

- **go-testing**, **angular-patterns**, **brescopack-conventions**: Not applicable to this Python project. Excluded from compact rules.
- No project-level skills detected.
