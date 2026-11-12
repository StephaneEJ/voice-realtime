"""N4 — page téléphone : appel vocal depuis le navigateur du téléphone.

`serveur.ServeurTelephone` sert la page et le canal WebSocket ;
`pont.PontAppel` relie un appel à n'importe quel fournisseur du protocole
`providers` ; `acces.VerificateurAcces` vérifie le jeton Cloudflare Access
quand la page est exposée.
"""
