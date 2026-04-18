# Documentation Process Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update repository documentation so `memory.md` becomes the source of truth for agent workflow rules while `README.md` exposes a concise human-facing process summary.

**Architecture:** Keep the detailed operating rules in `memory.md`, add a concise process summary to `README.md`, and preserve the new `docs/specs/` structure as the canonical feature-spec location. This keeps behavior rules centralized while making the workflow discoverable from the repo root.

**Tech Stack:** Markdown documentation, repository conventions

---

### Task 1: Update `memory.md`

**Files:**
- Modify: `memory.md`

- [ ] **Step 1: Draft the full replacement content**

Write a new `memory.md` that includes:
- coding pattern preferences
- a working memory protocol
- documentation requirements
- spec workflow rules
- a session notes section

- [ ] **Step 2: Show the proposed memory text in chat before editing**

Expected: the exact `memory.md` content is presented to the user for review before any file change.

- [ ] **Step 3: Replace `memory.md` with the approved content**

Expected: `memory.md` becomes the detailed source of truth for durable context and workflow rules.

- [ ] **Step 4: Display the full file after editing**

Run: `sed -n '1,260p' memory.md`
Expected: full updated file contents are shown in chat for verification.

### Task 2: Update `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a concise documentation/process section**

Include:
- `memory.md` as the detailed rules file
- `docs/specs/` as the canonical feature-spec location
- product-oriented docs living in `docs/`
- the expectation that README stays current as the repo evolves

- [ ] **Step 2: Preserve the existing lightweight overview**

Expected: `README.md` stays concise and does not gain detailed architecture content yet.

### Task 3: Verify the documentation state

**Files:**
- Check: `README.md`
- Check: `memory.md`
- Check: `docs/specs/2026-04-18-documentation-process-rules-design.md`

- [ ] **Step 1: Read back the updated files**

Run: `sed -n '1,220p' README.md`
Run: `sed -n '1,260p' memory.md`
Expected: the files reflect the approved design.

- [ ] **Step 2: Check git status**

Run: `git status --short`
Expected: only the intended documentation files are changed or added.
