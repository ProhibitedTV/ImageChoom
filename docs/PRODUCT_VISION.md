# ImageChoom Product Vision

ImageChoom is evolving from a curated workflow repository into a **GUI application** for building, running, and administering **Automatic1111 (A1111)** workflows backed by the **ChoomLang DSL**.

## North-star direction

- Provide a desktop-style operator experience for A1111 users.
- Keep ChoomLang as the canonical, portable workflow definition format.
- Make workflow administration first-class (not just ad-hoc script execution).

## What "GUI for ChoomLang + A1111" means

### 1) Workflow authoring and management
- Browse, create, duplicate, import, and export `.choom` workflows.
- Edit workflow variables (prompt, model, sampler, CFG, steps, seed, dimensions) in structured forms.
- Show underlying ChoomLang source side-by-side with form fields.
- Validate workflows before execution.

### 2) A1111 administration controls
- Configure one or more A1111 endpoints.
- Health-check endpoint availability and API compatibility.
- Manage default model/checkpoint overrides per workflow.
- Save reusable runtime presets and profile bundles.

### 3) Execution operations
- Run a workflow with live status/progress.
- Queue and batch execution support.
- Log requests/responses and execution metadata.
- Provide output gallery with links back to workflow + run config.

### 4) Reproducibility and governance
- Persist run history and workflow versions.
- Enable deterministic reruns by storing seed + full payload metadata.
- Encourage a repository-backed workflow library for teams.

## Near-term implementation milestones

1. Define an app architecture that wraps existing `workflows/` and `presets/` as data sources.
2. Add a machine-readable workflow manifest format for GUI indexing.
3. Implement endpoint and preset management screens.
4. Add run queue + history tracking.
5. Keep CLI parity by continuing to support `choom run` for every GUI-managed workflow.

## Non-goals (for now)

- Replacing the A1111 API itself.
- Introducing a proprietary workflow format separate from ChoomLang.
- Coupling workflows to a single model provider beyond A1111.

## Current state

Today, this repository still operates as a ChoomLang workflow collection and starter toolkit. The GUI direction above is the planned evolution path.
