import builtins
import importlib
import sys

import pytest


def test_cli_init_runs_without_chat_dependencies(monkeypatch, capsys):
    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in {"agent.runtime.graph", "agent.runtime.telegram_bot"}:
            raise ModuleNotFoundError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mira",
            "init",
            "acme-co",
            "--source-system",
            "stripe",
            "--tables",
            "invoice,customer,contact",
        ],
    )

    sys.modules.pop("agent.runtime.cli", None)
    cli = importlib.import_module("agent.runtime.cli")

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "company_id=acme-co" in out
    assert "run_id=" in out
