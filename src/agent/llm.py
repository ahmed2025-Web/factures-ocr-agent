"""Étape 8 — couche LLM interchangeable par configuration.

Tous les fournisseurs visés exposent une API **compatible OpenAI**, donc un seul
client (le SDK `openai`) suffit : on change juste l'URL, la clé et le modèle.
Le fournisseur se choisit avec la variable d'environnement LLM_PROVIDER, sans
toucher au code — c'est le critère central de l'étape 8.

Fournisseurs prévus :
  - "groq"       : hébergé, gratuit (GROQ_API_KEY)
  - "hyperfluid" : la gateway du projet (réutilise la clé OCR sk-hf), modèle chat-m
  - "ollama"     : modèle local (aucune clé)

LLM_MODEL permet de forcer un modèle précis ; sinon on prend le défaut du
fournisseur. Poser la même question avec deux configs différentes = deux LLM,
sans changer une ligne de code.
"""

import os

from openai import OpenAI

PROVIDERS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
    },
    "hyperfluid": {
        "base_url": None,  # vient de HYPERFLUID_LLM_URL
        "model": "gemma-4-12b",
    },
    "ollama": {
        "base_url": None,  # vient de OLLAMA_BASE_URL
        "model": "llama3.2",
    },
}


class LLM:
    """Client de chat, configuré pour un fournisseur donné."""

    def __init__(self, provider: str | None = None):
        provider = (provider or os.environ.get("LLM_PROVIDER", "groq")).lower()
        if provider not in PROVIDERS:
            raise ValueError(
                f"LLM_PROVIDER inconnu : {provider!r} (au choix : {', '.join(PROVIDERS)})"
            )
        cfg = PROVIDERS[provider]
        self.provider = provider
        self.model = os.environ.get("LLM_MODEL") or cfg["model"]
        self.client = OpenAI(
            base_url=self._base_url(provider, cfg),
            api_key=self._api_key(provider),
        )

    @staticmethod
    def _base_url(provider: str, cfg: dict) -> str:
        if provider == "hyperfluid":
            url = os.environ.get("HYPERFLUID_LLM_URL")
            if not url:
                raise SystemExit("HYPERFLUID_LLM_URL manquant dans .env.")
            return url.rstrip("/")
        if provider == "ollama":
            base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
            return base.rstrip("/") + "/v1"
        return cfg["base_url"]

    @staticmethod
    def _api_key(provider: str) -> str:
        if provider == "groq":
            key = os.environ.get("GROQ_API_KEY")
        elif provider == "hyperfluid":
            key = os.environ.get("HYPERFLUID_API_KEY") or os.environ.get("OCR_API_KEY")
        else:  # ollama : pas d'authentification, mais le SDK exige une valeur
            return "ollama"
        if not key:
            raise SystemExit(f"Clé API manquante pour le fournisseur {provider!r} (voir .env).")
        return key

    def chat(self, messages: list, tools: list):
        """Un tour de modèle. Retourne la réponse (format OpenAI)."""
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or None,
            tool_choice="auto" if tools else None,
            temperature=0,
        )


def get_llm(provider: str | None = None) -> LLM:
    return LLM(provider)
