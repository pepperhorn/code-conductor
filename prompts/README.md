# Conductor Implementation Prompts

These prompts are generated from `plan.md` for handing work to the two CLI agents:

- `claude-code-implementation.md`: build the v1 conductor with the full Claude Code adapter.
- `codex-cli-implementation.md`: implement the Codex adapter and lifecycle support behind the shared adapter interface.

Use `../IMPLEMENTATION_PLAN.md` as the execution order for the build.

The prompts include local CLI facts verified on 2026-06-28, plus env-driven local settings: `CONDUCTOR_PROJECT_ROOT=/home/shaun` and `CONDUCTOR_CHANNEL_SLOTS` defaulting to `5`. They still require build-time checks for behavior that can drift across CLI releases.
