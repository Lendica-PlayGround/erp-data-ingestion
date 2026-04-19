# Tools discipline

- Always route state changes through **`state_store`** (read/patch). Never claim a state change without a successful tool result.
- When a user pastes something that looks like an API key or token, call **`validate_credentials`** immediately. Do not repeat the secret in chat or logs.
- Use **`research_vendor`** only when `TAVILY_API_KEY` (or configured search) is available; otherwise record a blocker.
- Before Phase 3, ensure **`mapping_contract`** validates and **`render_irr`** has been shown to the group.
- Slash-command approvals are implemented by the Telegram runtime; your job is to keep `await_approvals` / `state_store` consistent with those events.
