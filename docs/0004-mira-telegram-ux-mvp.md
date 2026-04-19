# Mira Telegram UX — MVP

**Date:** April 19, 2026
**Scope:** Product + technical spec for how Mira behaves inside a Telegram onboarding group chat. Scopes the **MVP only**. Future phases (voice, reactions, multi-group routing, analytics, etc.) are intentionally out of scope.
**References:** `docs/0003-phase2-3-midlayer-agent.md` (§1.3, §2.4), `mira/agent/runtime/telegram_bot.py`, `mira/agent/runtime/session_memory.py`

---

## 1. Problem

Today Mira only replies in a Telegram group when:

- the message is a DM to the bot, or
- the message is a direct reply to one of the bot's messages, or
- the message contains an explicit `@mira_fwd_engineer_bot` mention (with `TELEGRAM_REQUIRE_MENTION=true`).

In a dedicated onboarding group (Customer + Mira + FDE), this feels wrong:

- Users must `@mira` on every message, which is unnatural.
- Mira ignores obvious answers to her own open question if the user forgets to reply-to or mention.
- Mira has no awareness of **who** is talking (customer vs FDE), so she cannot address or gate behavior by role.
- Every turn posts a visible `Mira heard you. Thinking...` placeholder, creating two messages per turn and channel noise.
- There is no way for humans to mute Mira for side chats and then resume her.
- Mira will reply even when the exchange clearly isn't for her, as long as she is mentioned.

## 2. Goals

Make Mira feel like a **third participant** in a dedicated onboarding group — not a slash-command CLI.

MVP goals:

1. No forced `@mira` mention. Mira decides when to speak.
2. Mira stays silent for human-to-human side chatter but still remembers it.
3. Mira knows sender role (Customer, FDE, Other) and uses that in prompts and gating.
4. Humans have clear, discoverable controls (`/status`, `/plan`, `/quiet`, `/resume`, plus existing approvals).
5. Channel noise is minimized (no placeholder message, use Telegram typing action).
6. Rate-limited so Mira cannot spam the group.

## 3. Non-goals (explicitly out of MVP)

- Voice / audio messages.
- Emoji reaction handling (e.g. 👍 = ack).
- Multi-group routing, cross-group dashboards, or group auto-provisioning.
- Sentiment / tone analysis.
- Proactive "nudge" timers (Mira re-pinging after silence).
- Mira joining Slack, Discord, or email.
- Inline keyboards / buttons for approvals.
- Any changes to Phase 2.5 approval semantics beyond what is in `0003`.

## 4. User stories

1. **Customer answers an open question without mentioning Mira.**
   Mira asked "Do you use Epicor cloud or on-prem?". Customer types "on-prem". Mira replies with the next step. No `@mira` needed.
2. **Customer and FDE chat to each other.**
   "James, can you confirm timeline?" — "Yeah, next week." Mira stays silent but logs the turn.
3. **Customer pastes an API key by accident.**
   Mira acknowledges receipt without echoing the key and advances to credential validation.
4. **FDE wants Mira muted while they side-discuss plan with customer.**
   FDE types `/quiet`. Mira confirms and stops auto-responding. Later `/resume` re-enables her.
5. **Anyone wants a quick state summary.**
   Types `/status` → concise: current phase, `next_question`, pending approvals, blockers.
6. **Anyone wants the recommended plan.**
   Types `/plan` → returns `recommended_plan.summary` + steps.
7. **Customer approves business meaning / FDE approves implementation.**
   Existing `/approve_customer` and `/approve_fde` keep working exactly as in `0003`.

## 5. Functional spec

### 5.1 Response policy

Mira responds if **any** of these is true (and not muted, see §5.4):

1. Slash command handled by Mira (`/status`, `/plan`, `/approve_customer`, `/approve_fde`, `/ping`, `/quiet`, `/resume`).
2. Direct reply to one of Mira's own messages.
3. Explicit `@mira_fwd_engineer_bot` mention.
4. **Answers an open question**: `OnboardingState.next_question` is non-empty **and** the sender is Customer or FDE **and** Mira's last message was recent (≤ N messages back or ≤ T minutes).
5. **High-signal onboarding content** in the message, detected by keyword heuristics already partially present in `session_memory.py`:
   - Known ERP / source names (`epicor`, `stripe`, `invoiced`, `google sheets`, …)
   - Access keywords (`api`, `oauth`, `sftp`, `csv`, `export`, `database dump`, `shared drive`, `on-prem`, `cloud`)
   - Credential-shaped tokens (matching a narrow pattern; the token value must **never** be echoed back)
   - A file/document attachment
6. Private 1:1 DM with the bot.

Otherwise Mira stays silent. She still:

- persists the turn into `conversation_history`,
- runs `maybe_capture_message_facts` to extract ERP / access hints.

### 5.2 Role awareness

- Sender role resolved from existing env vars:
  - `TELEGRAM_CUSTOMER_USER_IDS` → role = `customer`
  - `TELEGRAM_FDE_USER_IDS` → role = `fde`
  - else, if in `TELEGRAM_ALLOWLIST_USER_IDS` → role = `other`
  - else → reject with existing allowlist behavior.
- First time a role speaks, Mira writes a `StakeholderSummary` into `OnboardingState.stakeholder_context` (schema already supports it).
- Role is injected into the agent prompt as part of the state summary (`summarize_state_for_prompt`), e.g. "last_sender: customer (James)".
- Approval gating for `/approve_customer` vs `/approve_fde` remains as in `0003`.

### 5.3 Surface behavior

- Remove the `Mira heard you. Thinking...` placeholder message.
- Use `bot.send_chat_action(chat_id, "typing")` instead, repeated every ~4s until the reply is sent.
- Final reply is a single message, truncated to Telegram's limit (≤ 3500 chars to stay below the 4096 hard cap with safety margin).
- Long outputs split using the existing simple paragraph split if > 3500 chars; cap at 2 follow-up messages in MVP.
- No pinned intro message in MVP. `BOOTSTRAP.md` still runs exactly once on cold start per existing `should_include_bootstrap` gate.

### 5.4 Quiet / resume

New per-chat runtime flag stored on `OnboardingState` (new field, MVP scope):

```
ui_preferences:
  telegram:
    muted: bool = false
    muted_at: datetime | null
    muted_by_user_id: str | null
```

- `/quiet` sets `muted=true`. Mira replies once with `"Muted. I'll still watch and remember. /resume to turn me back on."` then stops replying to any non-slash message.
- While muted, slash commands still work (`/status`, `/plan`, `/resume`, `/approve_*`, `/ping`).
- `/resume` sets `muted=false` and Mira replies once to confirm.
- Only users in `TELEGRAM_CUSTOMER_USER_IDS`, `TELEGRAM_FDE_USER_IDS`, or `TELEGRAM_ALLOWLIST_USER_IDS` can toggle.

### 5.5 Rate limiting

- Minimum 3 seconds between two bot messages per chat.
- Maximum 10 bot messages per chat per minute.
- If limit hit, Mira silently drops the response and logs a warning. She does **not** queue-and-flush in MVP.

### 5.6 Slash commands (MVP set)

| Command | Who can run | Effect |
| :--- | :--- | :--- |
| `/status` | any allowlisted user | Renders short summary: state, `next_question`, open approvals, blockers |
| `/plan` | any allowlisted user | Renders `recommended_plan.summary` + first 5 steps |
| `/quiet` | allowlisted user | Mutes Mira in this chat |
| `/resume` | allowlisted user | Unmutes Mira |
| `/approve_customer` | `TELEGRAM_CUSTOMER_USER_IDS` | Existing, unchanged |
| `/approve_fde` | `TELEGRAM_FDE_USER_IDS` | Existing, unchanged |
| `/ping` | anyone | Existing, unchanged |

BotFather `/setcommands` list is seeded with these at setup time.

### 5.7 Safety rails (preserved)

- Allowlist enforcement stays exactly as today.
- Credential-shaped substrings are never echoed back in any reply (`/status`, `/plan`, or model output).
- Approvals remain role-gated via the existing env-var allowlists.
- Telegram privacy mode must be disabled (BotFather `/setprivacy → Disable`) for groups; setup doc notes this.

## 6. Technical design

### 6.1 Files touched

- `mira/agent/runtime/telegram_bot.py` — main changes:
  - Replace `_should_respond` with the §5.1 policy, taking `OnboardingState` as input.
  - Add `cmd_status`, `cmd_plan`, `cmd_quiet`, `cmd_resume`.
  - Add role resolver helper `resolve_sender_role(update) -> Literal["customer","fde","other"]`.
  - Swap `Mira heard you. Thinking...` for `send_chat_action("typing")` loop via `asyncio.create_task`.
  - Per-chat rate limiter (in-memory dict, chat_id → deque of timestamps).
- `mira/agent/models/onboarding.py` — add `TelegramUiPreferences` and `UiPreferences`, attach to `OnboardingState` with default factory. Back-compat: missing field loads as default.
- `mira/agent/runtime/session_memory.py`:
  - Add `message_has_onboarding_signal(text) -> bool` (keyword heuristic over existing `_SOURCE_PATTERNS` + `_ACCESS_PATTERNS` + file/credential regexes).
  - Add `answers_open_question(state, text, last_bot_turn_index) -> bool`.
  - Ensure `summarize_state_for_prompt` includes `last_sender` + `sender_role` + `muted` flag.
- `mira/agent/runtime/tools.py` — no behavioral change; only ensure no tool echoes credential substrings.
- `mira/agent/mira/USER.md` and `mira/agent/mira/TOOLS.md` — short note that role awareness is now available.
- Tests:
  - `mira/tests/test_telegram_policy.py` — unit tests for the response policy matrix (§5.1), mute toggling, rate limiter, role resolver.

### 6.2 State schema addition

```python
class TelegramUiPreferences(BaseModel):
    muted: bool = False
    muted_at: datetime | None = None
    muted_by_user_id: str | None = None

class UiPreferences(BaseModel):
    telegram: TelegramUiPreferences = Field(default_factory=TelegramUiPreferences)

class OnboardingState(BaseModel):
    ...
    ui_preferences: UiPreferences = Field(default_factory=UiPreferences)
```

### 6.3 Config

`.env` / `.env.example`:

```
TELEGRAM_REQUIRE_MENTION=false        # default changes to false for MVP
TELEGRAM_CUSTOMER_USER_IDS=...
TELEGRAM_FDE_USER_IDS=...
TELEGRAM_ALLOWLIST_USER_IDS=...
MIRA_TG_MIN_SECONDS_BETWEEN_REPLIES=3
MIRA_TG_MAX_REPLIES_PER_MINUTE=10
MIRA_TG_OPEN_QUESTION_WINDOW_MESSAGES=8
MIRA_TG_OPEN_QUESTION_WINDOW_SECONDS=900
```

### 6.4 Response policy pseudocode

```python
def should_respond(update, state, bot_username) -> bool:
    if is_slash_command(update):
        return True
    if is_private_chat(update):
        return True
    if state.ui_preferences.telegram.muted:
        return False
    if is_reply_to_bot(update, bot_username):
        return True
    if mentions_bot(update, bot_username):
        return True
    role = resolve_sender_role(update)
    if role in {"customer", "fde"}:
        if answers_open_question(state, update.message.text, within=window):
            return True
        if message_has_onboarding_signal(update.message.text) or has_attachment(update):
            return True
    return False
```

### 6.5 Failure modes

| Failure | Behavior |
| :--- | :--- |
| Rate limit exceeded | Silently drop, log warning, no retry |
| LLM call fails | Single user-visible error reply, not more |
| Attachment received but we can't parse in MVP | Short ack only, no parsing attempt |
| Muted but slash command run | Command works, confirmation reply allowed |
| Unknown command | Ignore (no "unknown command" reply, avoid noise) |

## 7. Acceptance criteria

Mira passes MVP when, in a freshly provisioned onboarding group:

1. Customer message `on-prem, version 11` right after Mira asks about deployment triggers a reply **without** `@mira`.
2. Two humans chatting unrelated content produces **no** bot reply, yet `/status` later shows the conversation logged and state unchanged.
3. `/quiet` silences Mira for subsequent free-text messages; `/resume` restores behavior; both toggles confirmed by exactly one bot message each.
4. Role gating: a non-customer user running `/approve_customer` gets the existing "Not authorized" reply.
5. Credentials pasted in the group are never echoed in any Mira reply including `/status` and `/plan`.
6. In a burst of 20 messages in 10 seconds from humans, Mira replies at most 10 times in the first minute and never two replies closer than 3 seconds apart.
7. No `Mira heard you. Thinking...` placeholder message appears at any point; instead, Telegram shows the "Mira is typing…" indicator while the model is running.
8. Existing `/ping`, `/approve_customer`, `/approve_fde` behaviors are unchanged.

## 8. Rollout

1. Land schema addition with default value and backwards-compatible load.
2. Land response-policy refactor behind env flag `MIRA_TG_SMART_POLICY=true` (default true). If false, falls back to legacy `_should_respond` for one release.
3. Update `.env.example`, `mira/README.md` (setup section) with BotFather privacy-mode instructions and new commands list.
4. Ship tests in `mira/tests/test_telegram_policy.py`.
5. Manual verification in a scratch Telegram group using `mira telegram` against a dev run.

## 9. Open questions

- Should `/quiet` time out automatically (e.g. auto-resume after 30 min)? **MVP answer:** no, manual resume only.
- Should Mira detect credential-shaped tokens server-side and redact from `conversation_history` too? **MVP answer:** yes for display; storage is a Phase 2 hardening item and out of MVP scope beyond "never echo back".
- Should `/status` be public to all group members or only allowlisted users? **MVP answer:** allowlisted only (consistent with existing approvals).
