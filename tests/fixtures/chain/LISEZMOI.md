# Enregistrements du mode chaîne (N2)

- `deux_phrases.wav`, `coupure.wav`, `killchat.wav` : voix française `say -v Thomas` sur bruit gaussien (graine fixe), PCM16 mono 16 kHz. Régénérables par `python3 scripts/generer_enregistrements_chaine.py` ; bornes attendues dans `enregistrements.json`.
- `jfk.wav` : voix humaine réelle, discours inaugural de J. F. Kennedy (1961, domaine public), copié des échantillons de whisper.cpp.
- `openai_chat_stream.sse` et `anthropic_messages_stream.sse` : flux de réponse écrits à la main au format documenté des deux API (Chat Completions en flux ; Messages en flux). Ils ne sont pas capturés sur les API réelles : aucun appel payant n'a été fait pour les produire.
