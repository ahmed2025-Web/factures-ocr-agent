"""Étape 8 — l'agent.

Répond en français aux questions sur les factures en utilisant UNIQUEMENT les
outils fournis (via un `ToolsBackend` : mock pour tester, serveur MCP ensuite).

Points demandés par l'étape 8 :
  - LLM interchangeable par configuration (voir llm.py) ;
  - l'utilisateur VOIT ce que fait l'agent : outils appelés, requêtes SQL, résultats ;
  - l'agent garde le fil de la conversation et s'arrête proprement ;
  - il ne doit pas inventer de chiffres : il répond à partir des résultats d'outils.
"""

import os
import re
import json

from .llm import get_llm
from .tools_backend import get_backend

MAX_STEPS = 10

SYSTEM_PROMPT = (
    "Tu es un assistant qui répond en français aux questions sur des factures. "
    "Utilise les outils pour obtenir les chiffres ; n'invente jamais de montant "
    "ni de nombre. Si une information n'est pas disponible via les outils, dis-le."
)


def run_agent(user_message: str, llm, backend, history: list) -> str:
    """Traite un message et renvoie la réponse. `history` est modifié en place."""
    history.append({"role": "user", "content": user_message})
    tools = backend.tools()

    for _ in range(MAX_STEPS):
        response = llm.chat(history, tools)
        message = response.choices[0].message
        history.append(message.model_dump())

        if not message.tool_calls:
            return _clean(message.content or "")

        for call in message.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            print(f"  ↳ outil : {call.function.name}({json.dumps(args, ensure_ascii=False)})")
            result = backend.call(call.function.name, args)
            for line in result.splitlines():
                print(f"      {line}")  # affiche le SQL exécuté et le résultat
            history.append({"role": "tool", "tool_call_id": call.id, "content": result})

    return "Arrêt : nombre maximum d'étapes atteint."


def _clean(text: str) -> str:
    """Retire les jetons de contrôle que certains modèles (ex. gemma) laissent fuiter.

    Enlève les balises de canal du style <|channel> et <channel|>, puis une
    éventuelle amorce « thought » restée en tête.
    """
    text = re.sub(r"<\|[a-zA-Z]*\|?>|<[a-zA-Z]*\|>", "", text).strip()
    if text.lower().startswith("thought"):
        text = text[len("thought"):].lstrip(" \n:")
    return text.strip()


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    llm = get_llm()
    backend = get_backend()
    history = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"Agent prêt — LLM : {llm.provider} ({llm.model}), outils : "
          f"{os.environ.get('AGENT_BACKEND', 'mock')}. Tape 'quit' pour quitter.\n")
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
        answer = run_agent(user_message, llm, backend, history)
        print(f"\nagent> {answer}\n")


if __name__ == "__main__":
    main()
