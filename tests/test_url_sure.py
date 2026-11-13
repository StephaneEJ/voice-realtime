"""N12 (revue du 12/11/2026) : aucune authentification en clair vers un hôte distant."""

from __future__ import annotations

import httpx
import pytest

from voice_realtime.providers.chain_stages import ChainConfigError, build_llm, build_stt, build_tts, parse_spec
from voice_realtime.tools.orchestrateur import ClientOrchestrateur, ErreurOrchestrateurClient
from voice_realtime.url_sure import UrlNonSure, verifier_url

ACCEPTEES = [
    "https://api.openai.com/v1",
    "https://orchestrateur.exemple.test/mcp",
    "http://127.0.0.1:8765/mcp",
    "http://127.8.9.10:11434/v1",
    "http://localhost:11434/v1",
    "http://LOCALHOST:11434/v1",
    "http://[::1]:8765/mcp",
]
REFUSEES = [
    "http://192.168.1.20:8765/mcp",
    "http://orchestrateur.exemple.test/mcp",
    "http://127.0.0.1.evil.example/v1",
    "http://localhost.evil.example/v1",
    "ftp://127.0.0.1/x",
    "ws://127.0.0.1:8765/mcp",
    "127.0.0.1:8765/mcp",
    "https:///sans-hote",
    "",
]


@pytest.mark.parametrize("url", ACCEPTEES)
def test_url_acceptees(url: str) -> None:
    assert verifier_url(url, "test") == url


@pytest.mark.parametrize("url", REFUSEES)
def test_url_refusees(url: str) -> None:
    with pytest.raises(UrlNonSure):
        verifier_url(url, "test")


def test_message_sans_identifiants_ni_chemin() -> None:
    with pytest.raises(UrlNonSure) as exc:
        verifier_url("http://moi:motdepasse@serveur.exemple.test/chemin?cle=abc", "orchestrateur")
    message = str(exc.value)
    assert "serveur.exemple.test" in message
    assert "motdepasse" not in message and "cle=abc" not in message and "/chemin" not in message


@pytest.mark.parametrize("construire,spec", [
    (build_llm, "openai:modele@http://serveur.exemple.test/v1"),
    (build_stt, "openai:whisper-1@http://10.0.0.5:8000/v1"),
    (build_tts, "openai:tts-1:alloy@http://serveur.exemple.test/v1"),
    (build_llm, "anthropic:claude@http://proxy.exemple.test"),
])
def test_etage_de_chaine_distant_non_chiffre_refuse(construire, spec: str) -> None:
    with pytest.raises(ChainConfigError, match="http://"):
        construire(spec, env={"OPENAI_API_KEY": "x", "ANTHROPIC_API_KEY": "x"})


def test_etage_de_chaine_local_et_chiffre_acceptes() -> None:
    assert parse_spec("openai:llama3@http://127.0.0.1:11434/v1").base_url == "http://127.0.0.1:11434/v1"
    assert parse_spec("openai:x@https://api.groq.com/openai/v1").base_url == "https://api.groq.com/openai/v1"


def test_orchestrateur_distant_non_chiffre_rien_ne_part() -> None:
    envois: list[httpx.Request] = []

    def transport(requete: httpx.Request) -> httpx.Response:
        envois.append(requete)
        return httpx.Response(200, json={})

    def helper(_commande: str) -> dict[str, str]:
        return {"Authorization": "Bearer jeton-de-test"}

    client = ClientOrchestrateur(url="http://192.168.1.20:8765/mcp", headers_helper="helper",
                                 transport=httpx.MockTransport(transport), lanceur_helper=helper)
    with pytest.raises(ErreurOrchestrateurClient, match="en clair"):
        client.appeler_outil("list_sessions", {})
    assert envois == []
