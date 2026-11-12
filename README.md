# synchro-annuaire

Met à jour chaque jour `annuaire.parquet` (MinIO, bucket `db-sd2`, colonnes `mail`, `affectation`) à partir du
CSV de l'annuaire du service. Les applications (Opsonium…) ne font que lire ce fichier.

```bash
python synchroniser_annuaire.py           # contrôle le CSV, n'envoie rien
python synchroniser_annuaire.py --apply   # envoie annuaire.parquet sur MinIO
```

Un CSV illisible, vide, de moins de 50 agents ou qui perd plus de 30 % des agents est rejeté : l'ancien
annuaire reste en place (`--force` pour passer outre la perte de 30 %). Dépendances : `pandas`, `pyarrow`, `boto3`.

## Synchronisation quotidienne (Forge)

1. Clés MinIO durables, limitées à la lecture et l'écriture de `db-sd2/annuaire.parquet`.
2. Settings → CI/CD → Variables (masquées) : `AWS_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
3. Build → Pipeline schedules : branche `main`, `0 6 * * 1-5`, fuseau de Paris. Premier lancement à la main :
   sans autre réglage, le job contrôle le CSV et n'envoie rien.
4. Une fois le contrôle réussi, ajouter à la planification `ANNUAIRE_OPTIONS` = `--apply`.

Le CSV passe par le proxy du lab (`ANNUAIRE_PROXY`) : `turgot.alize` n'est pas résolu depuis le pod du job.
