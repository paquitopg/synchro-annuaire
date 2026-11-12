---
title: "Le proxy de Nubonyxia filtre sur le User-Agent, destination par destination"
date: 2026-10-13
category: integration-issues
module: Sorties réseau depuis Nubonyxia
problem_type: integration_issue
component: infrastructure
symptoms:
  - "`Received HTTP code 403 from proxy after CONNECT` depuis le pod de l'application"
  - "« ProConnect est injoignable » sur la page de connexion"
  - "Le même appel réussit avec `curl` depuis un VSCode Nubonyxia"
root_cause: config_error
resolution_type: config_change
severity: high
retire_when: "Plus aucun appel ne sort par le proxy du lab (annuaire joint sans proxy, et application d'Opsonium passée à ProConnect RIE)."
tags: [proxy, user-agent, proconnect, nubonyxia, httr, "403"]
---

> Copie adaptée de la note d'opsonium-boostedCSVD. Les exemples ProConnect décrivent l'application Opsonium ; ici, seul compte le `User-Agent` envoyé par `synchroniser_annuaire.py` (constante `USER_AGENT`).

# Le proxy de Nubonyxia filtre sur le User-Agent, destination par destination

## Problem

Pour joindre ProConnect Internet depuis Nubonyxia, l'application passe par le proxy HTTP du lab.
Celui-ci acceptait la production ProConnect mais refusait la plateforme d'intégration, alors que le
même test lancé à la main depuis un VSCode passait pour les deux.

## Symptoms

- `Received HTTP code 403 from proxy after CONNECT` vers `fca.integ01.dev-agentconnect.fr`.
- `200` vers `auth.agentconnect.gouv.fr` depuis le même pod, avec le même code.
- `200` vers les deux hôtes avec `curl` depuis un VSCode Nubonyxia.

## What Didn't Work

- Valider l'accès avec `curl` depuis un VSCode : il n'envoie pas le même `User-Agent` que
  l'application, donc sa réussite ne dit rien du pod.
- Demander une ouverture de flux : le flux était ouvert, c'est l'en-tête qui était refusé.

## Solution

Envoyer `User-Agent: curl/8.5.0` sur les appels sortants. Dans l'application, c'est le défaut du
paramètre `PROCONNECT_USER_AGENT` (`app/proconnect.R`), modifiable dans les secrets du runner sans
reconstruire l'image. `synchroniser_annuaire.py` fait de même pour atteindre l'annuaire (`USER_AGENT`, tunnel `CONNECT` par `ANNUAIRE_PROXY`).

Pour tester, se placer dans le pod de l'application, avec le `User-Agent` qu'elle envoie :

```bash
kubectl exec -n <namespace> "$POD" -- Rscript -e '
p <- httr::use_proxy("http://172.16.0.53:3128")
ua <- httr::user_agent("curl/8.5.0")
u <- "https://fca.integ01.dev-agentconnect.fr/api/v2/.well-known/openid-configuration"
cat(tryCatch(httr::status_code(httr::GET(u, p, ua)), error = conditionMessage), "\n")'
```

## Why This Works

Le proxy applique des règles qui dépendent à la fois de la destination et du `User-Agent` de la
requête `CONNECT`. Celui de R (`libcurl/… r-curl/… httr/…`) n'est pas accepté vers tous les hôtes ;
celui de `curl` l'est vers ceux dont l'application a besoin.

## Prevention

- Un test réseau n'a de valeur que lancé depuis le pod concerné, avec le client et le `User-Agent`
  réellement utilisés.
- Un `403` qui réapparaît après un changement de règle du proxy : refaire le test avec d'autres
  valeurs de `User-Agent`, puis changer `PROCONNECT_USER_AGENT`.
- Garder les commandes collées dans un terminal sur des lignes courtes : un retour à la ligne
  glissé dans un nom d'hôte donne lui aussi un `403`.

## Related Issues

- Historique : opsonium-boostedCSVD, plan de mise en service de ProConnect, étape 3.
- [runner-forge-ne-resout-pas-turgot.md](runner-forge-ne-resout-pas-turgot.md).
