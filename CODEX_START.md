# Starting prompt for Codex

Copy the instruction below into Codex after extracting this package into the project root.

---

Implement the application described in this repository's planning package on my local Ubuntu machine.

Read AGENTS.md first and follow its SOLID, clean-code, dependency-boundary, async-lifecycle, testing, and reporting rules. Then read MAIN_PLAN.md, ARCHITECTURE.md, SOURCES.md, PROGRESS.md, and the relevant plans/Pxx file.

Resume from the earliest unfinished phase slice whose prerequisites are satisfied, using the
current status in PROGRESS.md and the relevant subplan. Do not redo completed P01 work or erase
the tested offline P02–P04 slices. Use LiveKit CLI for the local workflow. The target remains one
active interview, one local LiveKit room, two separate AgentSession instances and two different
agents. HR runs first. Its scoring proceeds in the background while the Staff Engineer session
runs in the same room. The technical interviewer can see attributed HR questions and answers.
Use OpenRouter Sonnet 5 for every LLM task and ElevenLabs for STT/TTS, with a distinct voice for
each agent.

Preserve every fixed requirement in MAIN_PLAN.md. Verify installed APIs, model availability and CLI flags instead of inventing them. A roomless console test is not a room-based acceptance test. Do not silently replace two sessions with one, change providers, add cloud deployment, or build a candidate web frontend.

Build in small complete slices, run meaningful tests, and update PROGRESS.md with actual evidence after each phase. Keep going through ready work without asking me to approve routine implementation steps. If a live gate is blocked by missing credentials or hardware, continue safe independent work and report exactly what input is needed; do not mark that gate passed. I will supply secrets and voice IDs locally.

The completion deliverable is runnable local code, a tested Ubuntu runbook, and honest acceptance
results. Begin by inspecting current code and PROGRESS.md, then implement the next ready slice.
P00's remaining live gates should be resumed only when host audio and credentials are available.

---

For a single-phase task, use the Codex task prompt at the end of its subplan and explicitly limit execution to that phase. Keep AGENTS.md at the repository root for all phases.
