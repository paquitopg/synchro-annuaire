---
title: "Le job planifié de la Forge ne résout pas turgot.alize : passer par le proxy du lab"
date: 2026-10-13
category: integration-issues
module: Synchronisation de l'annuaire
problem_type: integration_issue
component: background_job
symptoms:
  - "Le job `synchro-annuaire` échoue au téléchargement du CSV : nom d'hôte `turgot.alize` introuvable"
  - "Le même script fonctionne lancé à la main depuis un VSCode Nubonyxia"
  - "La planification ne se déclenche pas certains jours, sans erreur"
root_cause: config_error
resolution_type: config_change
severity: medium
tags: [forge, gitlab-ci, pipeline-planifie, dns, proxy, annuaire]
---

# Le job planifié de la Forge ne résout pas turgot.alize : passer par le proxy du lab

## Problem

`synchroniser_annuaire.py` télécharge l'annuaire sur `turgot.alize`. Depuis un VSCode Nubonyxia le
script fonctionnait ; lancé par le pipeline planifié de la Forge, il ne trouvait pas l'hôte.

## Symptoms

- Échec de résolution de `turgot.alize` dans le journal du job.
- Aucun échec depuis un VSCode, qui a `https_proxy` dans son environnement.

## What Didn't Work

- Supposer que le pod du job a le même réseau qu'un VSCode : il n'a ni le même DNS ni de variable
  `https_proxy`.

## Solution

Faire passer le téléchargement par le proxy du lab, avec une variable propre au script pour ne pas
détourner les autres appels du job (MinIO et le Nexus restent en direct). Dans
`.gitlab-ci.yml` :

```yaml
variables:
  ANNUAIRE_PROXY: "http://172.16.0.53:3128"
```

Le script lit `ANNUAIRE_PROXY`, puis `https_proxy` à défaut.

## Why This Works

Le DNS du cluster ne connaît pas `turgot.alize`. Le proxy, lui, le résout : en lui confiant la
requête, le pod n'a plus besoin de résoudre le nom.

## Prevention

Ce qu'un job de la Forge sur Nubonyxia doit réunir pour tourner, et qui ne se lit pas dans le code :

- **Un runner avec le tag `nubonyxia` doit être disponible pour le projet.** Sans lui, la planification
  ne part pas et personne n'est prévenu.
- `pip` passe par le Nexus, avec un bundle d'autorités qui ajoute celle du ministère
  (`mefr-ca.crt`) aux autorités publiques.
- Un hôte interne injoignable depuis un job : essayer le proxy avant de demander une ouverture de flux.

## Related Issues

- Historique : cette note vient d'opsonium-boostedCSVD (pull request #7 `fix/synchro-annuaire-proxy`), d'où le job
  a été extrait. Le même proxy filtre sur le `User-Agent` (`proxy-nubonyxia-filtre-user-agent.md` dans ce dépôt).
