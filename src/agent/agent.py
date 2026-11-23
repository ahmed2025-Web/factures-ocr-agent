"""Étape 8 — l'agent.

Répond en français aux questions sur les factures en utilisant UNIQUEMENT les
outils du serveur MCP (étape 7). Le LLM est interchangeable (voir llm.py).

L'utilisateur doit VOIR ce que fait l'agent : outils appelés, requêtes SQL,
résultats. L'agent garde le fil de la conversation et s'arrête proprement.

Base reprise de notre agent initial : la boucle (modèle ↔ outils) est prête ;
reste à brancher les vrais outils exposés par le serveur MCP.
"""

import os
import json

from .llm import get_llm

MAX_STEPS = 10

SYSTEM_PROMPT = (
    "Tu es un assistant qui répond en français aux questions sur des factures. "
    "Tu réponds UNIQUEMENT à partir des résultats des outils ; n'invente jamais "
    "de chiffres. Si tu n'as pas l'information, dis-le."
)


def get_mcp_tools() -> list:
    """Retourne les outils exposés par le serveur MCP (étape 7), au format du LLM."""
    # TODO étape 8 : se connecter au serveur MCP et convertir ses outils.
    return []


def run_mcp_tool(name: str, arguments: dict) -> str:
    """Exécute un outil MCP et retourne son résultat en texte."""
    # TODO étape 8 : router l'appel vers le serveur MCP.
    raise NotImplementedError("brancher les outils du serveur MCP (étape 7)")


def run_agent(user_message: str, llm, tools: list) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    for _ in range(MAX_STEPS):
        response = llm.chat(messages, tools)
        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:
            return message.content or ""

        for call in message.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            # Transparence : montrer à l'utilisateur ce que fait l'agent.
            print(f"[outil] {call.function.name}({json.dumps(args, ensure_ascii=False)})")
            result = run_mcp_tool(call.function.name, args)
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": result}
            )

    return "Arrêt : nombre maximum d'étapes atteint."


def main() -> None:
    llm = get_llm()
    tools = get_mcp_tools()
    print(f"Agent prêt (LLM : {os.environ.get('LLM_PROVIDER', 'groq')}). 'quit' pour quitter.\n")
    while True:
        try:
            user_message = input("vous> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_message.lower() in {"quit", "exit"}:
            break
        if not user_message:
            continue
        print(f"\nagent> {run_agent(user_message, llm, tools)}\n")


if __name__ == "__main__":
    main()
