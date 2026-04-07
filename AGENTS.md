# Agent Instructions

## Before Starting Any Work

1. Read `CLAUDE.md` for project rules, environment, and available models/tools.
2. Read `Codex_Development_Tasks.md` for task specifications and priority order.
3. Read `Library_of_Longing_Masterplan.md` for full project concept and design.

## Development Order

Start with **C8 (Scene Config System)** — all other scripts depend on it.
Follow the numbered order in Section D of `Codex_Development_Tasks.md`.

## Key Rules

- All code, comments, variable names: **English**
- Scripts go in `scripts/`, workflows in `workflows/`, configs in `scenes/`
- Each script must work standalone (`if __name__ == "__main__":` with demo)
- Use `scenes/001_grandma_porch_summer.yaml` as test input
- Reference code in `C:\Users\sinmb\workspace\scp-videos\` is **read-only**
- All models and dependencies are already installed — do not reinstall
