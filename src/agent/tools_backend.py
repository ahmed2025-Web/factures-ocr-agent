"""Étape 8 — d'où viennent les outils de l'agent.

L'agent ne doit utiliser QUE les outils du serveur MCP (étape 7). Comme ce
serveur est développé en parallèle (partie de Salma), on met ici une petite
abstraction `ToolsBackend` avec deux implémentations :

  - MockBackend : de fausses factures, pour tester l'agent dès maintenant
    (la boucle, l'interchangeabilité du LLM, l'affichage des outils + SQL) ;
  - McpBackend  : le vrai branchement au serveur MCP, à compléter quand il existe.

Passer de l'un à l'autre = changer AGENT_BACKEND, sans toucher à l'agent.
"""

import os
import json

# --- Fausses données, juste pour la démo hors MCP --------------------------------
_FAKE_INVOICES = [
    {"numero": "A-2025-0001", "fournisseur": "Aubry", "annee": 2025, "statut": "Payée", "ttc": 1200.00},
    {"numero": "A-2025-0003", "fournisseur": "Aubry", "annee": 2025, "statut": "En retard", "ttc": 7567.26},
    {"numero": "BS-2025-0002", "fournisseur": "Bernard", "annee": 2025, "statut": "En retard", "ttc": 4320.50},
    {"numero": "A-2026-0002", "fournisseur": "Aubry", "annee": 2026, "statut": "Envoyée", "ttc": 980.00},
]


class ToolsBackend:
    """Interface commune : lister les outils et en exécuter un."""

    def tools(self) -> list:
        raise NotImplementedError

    def call(self, name: str, arguments: dict) -> str:
        raise NotImplementedError


class MockBackend(ToolsBackend):
    """Backend de test : deux outils sur de fausses factures.

    Chaque réponse montre la requête SQL « exécutée », pour la transparence
    (comme le fera le vrai serveur MCP).
    """

    def tools(self) -> list:
        return [
            _tool("compter_et_totaliser",
                  "Nombre et total TTC des factures, avec filtres optionnels.",
                  {"annee": {"type": "integer"}, "statut": {"type": "string"}}),
            _tool("lister_factures",
                  "Liste des factures correspondant aux filtres.",
                  {"annee": {"type": "integer"}, "statut": {"type": "string"}}),
        ]

    def call(self, name: str, arguments: dict) -> str:
        rows = _filter(arguments.get("annee"), arguments.get("statut"))
        where, sql_tail = _where(arguments)
        if name == "compter_et_totaliser":
            total = sum(r["ttc"] for r in rows)
            sql = f"SELECT count(*), sum(ttc) FROM factures{sql_tail}"
            return (f"SQL exécuté : {sql}\n"
                    f"Résultat : {len(rows)} facture(s), total TTC {total:.2f} €")
        if name == "lister_factures":
            sql = f"SELECT numero, fournisseur, statut, ttc FROM factures{sql_tail}"
            lignes = "\n".join(
                f"- {r['numero']} | {r['fournisseur']} | {r['statut']} | {r['ttc']:.2f} €"
                for r in rows
            ) or "(aucune)"
            return f"SQL exécuté : {sql}\nRésultat :\n{lignes}"
        return f"Erreur : outil inconnu {name!r}."


class McpBackend(ToolsBackend):
    """Vrai branchement au serveur MCP de l'étape 7 — à compléter."""

    def tools(self) -> list:
        raise NotImplementedError("TODO : se connecter au serveur MCP et exposer ses outils")

    def call(self, name: str, arguments: dict) -> str:
        raise NotImplementedError("TODO : router l'appel vers le serveur MCP")


def get_backend() -> ToolsBackend:
    """Choisit le backend d'outils selon AGENT_BACKEND (mock par défaut)."""
    kind = os.environ.get("AGENT_BACKEND", "mock").lower()
    if kind == "mock":
        return MockBackend()
    if kind == "mcp":
        return McpBackend()
    raise ValueError(f"AGENT_BACKEND inconnu : {kind!r}")


# --- Helpers ---------------------------------------------------------------------
def _tool(name: str, description: str, properties: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties},
        },
    }


def _filter(annee, statut) -> list:
    rows = _FAKE_INVOICES
    if annee is not None:
        rows = [r for r in rows if r["annee"] == int(annee)]
    if statut:
        rows = [r for r in rows if r["statut"].lower() == str(statut).lower()]
    return rows


def _where(arguments: dict) -> tuple[str, str]:
    conds = []
    if arguments.get("annee") is not None:
        conds.append(f"annee = {int(arguments['annee'])}")
    if arguments.get("statut"):
        conds.append(f"statut = {json.dumps(str(arguments['statut']), ensure_ascii=False)}")
    tail = (" WHERE " + " AND ".join(conds)) if conds else ""
    return " AND ".join(conds), tail
