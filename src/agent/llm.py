"""Étape 8 — couche LLM interchangeable par configuration.

Le fournisseur est choisi via la variable d'environnement LLM_PROVIDER
(ex. "groq" hébergé, "ollama" local). Pour en ajouter un, implémenter une
fonction `chat(messages, tools)` et l'enregistrer dans get_llm().

But : poser la MÊME question avec deux LLM différents SANS changer le code.
"""

import os


def get_llm():
    """Retourne l'objet LLM correspondant à LLM_PROVIDER."""
    provider = os.environ.get("LLM_PROVIDER", "groq").lower()
    if provider == "groq":
        return GroqLLM()
    if provider == "ollama":
        return OllamaLLM()
    raise ValueError(f"LLM_PROVIDER inconnu : {provider!r}")


class GroqLLM:
    """LLM hébergé via Groq (API gratuite, style OpenAI)."""

    model = "llama-3.3-70b-versatile"

    def __init__(self):
        from groq import Groq

        self.client = Groq()  # lit GROQ_API_KEY

    def chat(self, messages: list, tools: list):
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=1024,
        )


class OllamaLLM:
    """LLM local via Ollama (même interface chat/tools, style OpenAI)."""

    model = "llama3.2"

    def __init__(self):
        raise NotImplementedError(
            "TODO étape 8 : implémenter le client Ollama (OLLAMA_BASE_URL) "
            "avec la même interface .chat(messages, tools)"
        )

    def chat(self, messages: list, tools: list):  # pragma: no cover
        ...
