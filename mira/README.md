# Mira — Phase 2–3 implementation

All code for the onboarding agent (LangGraph runtime, skills, connector framework, published schemas, Supabase migrations, and tests) lives under this folder so the rest of the repo stays focused on apps, seeds, and product docs.

| Path | Purpose |
|------|---------|
| `agent/` | Bootstrap markdown, `skills/`, runtime, stores, models, CLI entrypoint (`mira`) |
| `framework/` | Shared connector library used by generated packages |
| `schemas/` | Published `midlayer/v1` + `mapping_contract` JSON Schemas |
| `midlayer/` | Pydantic models + schema sources (installable as `midlayer`) |
| `supabase/migrations/` | Control-plane SQL |
| `connectors/` | Placeholder for generated per-source packages (also written under `.mira_workspace/` at runtime) |
| `tests/` | Agent unit tests |

Install from the **repository root** (parent of `mira/`): `pip install -e ".[dev]"`. Python import names are unchanged (`agent`, `framework`, `midlayer`).

## Telegram Setup Notes

For onboarding groups, disable Telegram privacy mode in BotFather (`/setprivacy` -> `Disable`) so Mira can observe normal group replies without forced mentions.

Seed BotFather `/setcommands` with:

- `/ping`
- `/status`
- `/plan`
- `/quiet`
- `/resume`
- `/approve_customer`
- `/approve_fde`

Runtime defaults for the MVP Telegram UX live in `.env.example`, including `TELEGRAM_REQUIRE_MENTION=false`, `MIRA_TG_SMART_POLICY=true`, and the per-chat reply rate limits.
