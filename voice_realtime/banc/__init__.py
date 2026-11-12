"""Banc d'essai N3 : harnais, métriques et rapport de comparaison des fournisseurs vocaux.

Le banc rejoue des scénarios enregistrés (voix, coupure, outils, mot d'arrêt)
sur des candidats (mode chaîne ou fournisseur temps réel) et mesure : latence
de première réponse, qualité en français, coupure de parole, appels d'outils
et coût à l'heure.

Par défaut, il tourne **à blanc** : seuls des étages simulés ou locaux et
gratuits sont joués, toute connexion réseau hors boucle locale est refusée,
et les candidats payants sont seulement chiffrés. Un passage payant exige un
budget validé, une autorisation explicite et n'a jamais lieu la nuit.
"""
