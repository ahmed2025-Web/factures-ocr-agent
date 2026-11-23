"""Branchement agent ↔ MCP : le backend « mcp » de l'agent voit et appelle les vrais outils."""

import os


def test_backend_mcp(data_root, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", data_root)
    from src.agent.tools_backend import McpBackend

    backend = McpBackend()
    try:
        names = {t["function"]["name"] for t in backend.tools()}
        assert "compter_et_totaliser" in names and "requete_sql" in names
        out = backend.call("compter_et_totaliser", {"statut": "En retard", "annee": 2025})
        assert out.startswith("SQL exécuté : SELECT count(*)")
        assert '"total_ttc": "7567.26"' in out
    finally:
        backend.close()
