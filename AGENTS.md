# synchro-annuaire : consignes pour les agents

Script Python + pipeline planifié (voir [README.md](README.md)). Ne jamais afficher, écrire ni committer un
secret (clés MinIO dans les variables CI/CD de la Forge).

Le dépôt de référence est la **Forge** (`main` protégé, merge request, fusion en avance rapide) ; le `main` de
GitHub n'en est que le miroir. Flux : `git forge-pull` (Nubonyxia), `git feat <nom>` (SSPCloud), `git ship <nom>`
(Nubonyxia), merge request. Ne jamais pousser sur le `main` de la Forge.
