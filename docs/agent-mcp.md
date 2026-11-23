# L'agent et ton serveur MCP (pour Salma)

Petit point sur où en est l'agent (étape 8) et comment il se branchera sur ton
serveur MCP (étape 7).

## Ce qui est fait côté agent

L'agent est codé et **testé en vrai** : il parle à un LLM (via une config
interchangeable), il appelle des outils, il affiche le SQL exécuté et le
résultat, puis répond en français.

**Mais** pour l'instant les outils ne tapent pas dans les vraies données : ils
viennent d'un **backend « mock »** (de fausses factures écrites en dur, dans
`src/agent/tools_backend.py` → classe `MockBackend`). C'était juste pour valider
la mécanique de l'agent sans attendre le reste.

## Ce qui se passera quand ton MCP sera prêt

Rien à changer dans l'agent lui-même : il y a déjà un emplacement prévu, la
classe **`McpBackend`** dans le même fichier (`src/agent/tools_backend.py`), pour
l'instant vide. Il suffira de :

1. la compléter pour qu'elle se connecte à ton serveur MCP et expose ses outils ;
2. lancer l'agent avec `AGENT_BACKEND=mcp` (au lieu de `mock`).

Et là on passe du test au réel : l'agent répond avec les vraies factures.

## Ce dont l'agent a besoin de ton côté

Ton serveur MCP doit exposer des outils pour : lister / compter / totaliser les
factures (avec filtres), le détail d'une facture, le schéma, et une requête SQL
en lecture seule. **Important** : que chaque outil renvoie aussi la **requête SQL
exécutée** — l'agent sait déjà l'afficher (c'est le critère de transparence).

En résumé : toi tu fais le MCP (étape 7), et le branchement à l'agent, c'est juste
remplir `McpBackend` + changer une variable. 🙂

## Mise à jour : c'est branché

`McpBackend` est complété (session stdio vers `src.mcp_server.server`). Avec
`AGENT_BACKEND=mcp`, l'agent utilise les 6 outils réels et affiche le SQL
exécuté avec ses paramètres. Test : `tests/test_agent_mcp.py`. Détails des
outils et de la sécurité : [docs/mcp.md](mcp.md).
