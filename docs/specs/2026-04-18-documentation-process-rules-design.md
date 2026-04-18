# Documentation And Process Rules Design

**Date:** April 18, 2026
**Scope:** Define how repository documentation, memory management, and feature-spec workflow should be maintained.

## Goal

Establish a lightweight but explicit documentation process so both the agent and human collaborators can keep project context, specs, and product-facing explanations current as the codebase evolves.

## Decisions

### 1. `memory.md` is the source of truth for agent workflow rules

`memory.md` will store:
- coding pattern preferences
- durable project context and decisions
- rules for updating memory after interactions
- a running account of attempted approaches and outcomes
- documentation obligations after code changes
- the feature-spec workflow requirement

This keeps detailed operating instructions in one place instead of duplicating them across multiple files.

### 2. `README.md` will contain a concise human-facing process summary

`README.md` will remain an overview document for the repository, but it will also gain a short section that explains:
- `memory.md` contains working rules and durable context
- `docs/specs/` is the canonical location for feature specs
- product-oriented documentation should be maintained in `docs/`
- the README must be updated as the repository evolves

### 3. Specs must be written before feature implementation

For any new feature or behavior change:
- create a spec under `docs/specs/`
- use the brainstorming workflow as the design gate before implementation
- treat the approved spec as the implementation reference

This should apply going forward as a standing process rule for the repository.

### 4. Product documentation should exist separately from technical specs

The repository should maintain product-oriented documents in `docs/` that explain what a feature or workflow does from the product perspective, not only the technical implementation perspective.

## File Changes

### `memory.md`

Add:
- working-memory rules
- session-notes guidance for recording what was tried
- post-implementation communication requirements
- documentation upkeep requirements
- spec-writing workflow rules

### `README.md`

Add a short documentation/process section that references:
- `memory.md`
- `docs/specs/`
- product docs in `docs/`

### `docs/specs/`

Ensure this directory exists and is used for specs going forward.

## Boundaries

- Do not add detailed architecture content in `README.md` yet.
- Do not create a full product document in this change unless needed to establish the process rule.
- Keep the new process documentation concise and maintainable.

## Risks

- Duplicating rules between `memory.md` and `README.md` can cause drift, so `memory.md` should remain the detailed source of truth.
- If session-note expectations are too verbose, `memory.md` can become noisy. The guidance should emphasize durable and useful notes rather than logging everything.

## Success Criteria

- `memory.md` clearly defines how memory should be maintained.
- `README.md` tells contributors where process and spec documentation live.
- `docs/specs/` exists and is referenced as the default spec location.
- The workflow is explicit enough that future feature work starts with a written spec.
