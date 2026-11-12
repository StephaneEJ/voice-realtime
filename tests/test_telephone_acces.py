"""N4 — vérification locale du jeton Cloudflare Access, avec des clés générées."""

from __future__ import annotations

import time

import pytest

from tests.faux_telephone import ADRESSE, AUD, EMETTEUR, EQUIPE, CleAccess
from voice_realtime.telephone.acces import AccesRefuse, VerificateurAcces, cles_depuis_jwks, normaliser_equipe


@pytest.fixture(scope="module")
def cle() -> CleAccess:
    return CleAccess()


def verificateur(*cles: CleAccess, lectures: list[int] | None = None) -> VerificateurAcces:
    jeu = {"keys": [c.jwk() for c in cles]}

    def lire() -> dict:
        if lectures is not None:
            lectures.append(1)
        return jeu

    v = VerificateurAcces.construire(EQUIPE, AUD, [ADRESSE.upper()], lire_jwks=lire)
    v.charger_cles(force=True)
    return v


def test_jeton_valide_rend_l_adresse(cle: CleAccess) -> None:
    assert verificateur(cle).verifier(cle.jeton()) == ADRESSE


@pytest.mark.parametrize(
    ("charge", "motif"),
    [
        ({"exp": int(time.time()) - 120}, "jeton_expire"),
        ({"exp": "demain"}, "jeton_expire"),
        ({"nbf": int(time.time()) + 600}, "jeton_premature"),
        ({"iss": "https://autre.cloudflareaccess.com"}, "emetteur_refuse"),
        ({"aud": ["autre-application"]}, "audience_refusee"),
        ({"aud": AUD}, None),  # audience en chaîne simple : acceptée
        ({"email": "intrus@example.org"}, "adresse_refusee"),
        ({"email": ""}, "adresse_refusee"),
    ],
)
def test_revendications_controlees(cle: CleAccess, charge: dict, motif: str | None) -> None:
    v = verificateur(cle)
    if motif is None:
        assert v.verifier(cle.jeton(**charge)) == ADRESSE
        return
    with pytest.raises(AccesRefuse) as err:
        v.verifier(cle.jeton(**charge))
    assert err.value.motif == motif


def test_signature_d_une_autre_cle_refusee(cle: CleAccess) -> None:
    intruse = CleAccess(kid=cle.kid)  # même kid, autre clé privée
    with pytest.raises(AccesRefuse) as err:
        verificateur(cle).verifier(intruse.jeton())
    assert err.value.motif == "signature_invalide"


def test_charge_modifiee_apres_signature_refusee(cle: CleAccess) -> None:
    tete, _, signature = cle.jeton().split(".")
    autre = cle.jeton(email="intrus@example.org").split(".")[1]
    with pytest.raises(AccesRefuse) as err:
        verificateur(cle).verifier(f"{tete}.{autre}.{signature}")
    assert err.value.motif == "signature_invalide"


@pytest.mark.parametrize(
    ("jeton", "motif"),
    [(None, "jeton_absent"), ("", "jeton_absent"), ("abc", "jeton_malforme"), ("a.b.c", "jeton_malforme")],
)
def test_jetons_absents_ou_malformes(cle: CleAccess, jeton: str | None, motif: str) -> None:
    with pytest.raises(AccesRefuse) as err:
        verificateur(cle).verifier(jeton)
    assert err.value.motif == motif


def test_algorithme_none_ou_hs256_refuse(cle: CleAccess) -> None:
    v = verificateur(cle)
    for alg in ("none", "HS256"):
        with pytest.raises(AccesRefuse) as err:
            v.verifier(cle.jeton(entete={"alg": alg}))
        assert err.value.motif == "algorithme_refuse"


def test_rotation_des_cles_relit_le_jwks_une_fois(cle: CleAccess) -> None:
    nouvelle = CleAccess(kid="cle-2")
    jeux = [{"keys": [cle.jwk()]}, {"keys": [cle.jwk(), nouvelle.jwk()]}]
    lectures: list[int] = []

    def lire() -> dict:
        lectures.append(1)
        return jeux[min(len(lectures) - 1, 1)]

    v = VerificateurAcces.construire(EQUIPE, AUD, [ADRESSE], lire_jwks=lire)
    v.charger_cles(force=True)
    v._derniere_lecture = float("-inf")  # la minute de garde est passée
    assert v.verifier(nouvelle.jeton()) == ADRESSE
    assert len(lectures) == 2
    # kid inconnu juste après : pas de nouvelle lecture (garde d'une minute).
    with pytest.raises(AccesRefuse) as err:
        v.verifier(CleAccess(kid="cle-3").jeton())
    assert err.value.motif == "cle_inconnue"
    assert len(lectures) == 2


def test_cles_illisibles_au_controle(cle: CleAccess) -> None:
    def lire() -> dict:
        raise OSError("réseau")

    v = VerificateurAcces.construire(EQUIPE, AUD, [ADRESSE], lire_jwks=lire)
    with pytest.raises(AccesRefuse) as err:
        v.verifier(cle.jeton())
    assert err.value.motif == "cles_indisponibles"


def test_jwks_filtre_les_cles_inutilisables(cle: CleAccess) -> None:
    jwk = cle.jwk()
    jeu = {"keys": [jwk, {**jwk, "kid": "chiffrement", "use": "enc"}, {"kty": "EC", "kid": "ec"}, {"kty": "RSA"}]}
    assert set(cles_depuis_jwks(jeu)) == {cle.kid}


def test_construction_et_equipe() -> None:
    assert normaliser_equipe("essai") == EMETTEUR
    assert normaliser_equipe("https://essai.cloudflareaccess.com/") == EMETTEUR
    with pytest.raises(ValueError):
        normaliser_equipe("  ")
    with pytest.raises(ValueError):
        VerificateurAcces.construire(EQUIPE, "", [ADRESSE], lire_jwks=dict)
    with pytest.raises(ValueError):
        VerificateurAcces.construire(EQUIPE, AUD, [" "], lire_jwks=dict)
