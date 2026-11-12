"""Met à jour annuaire.parquet (MinIO, bucket db-sd2) à partir de l'annuaire du service.

Lancé chaque jour par le pipeline planifié de la Forge (job `synchro-annuaire` de
.gitlab-ci.yml), ou à la main depuis un VSCode Nubonyxia ayant accès au bucket db-sd2.

    python synchroniser_annuaire.py
        -> télécharge et contrôle le CSV, affiche le bilan sans rien envoyer
    python synchroniser_annuaire.py --apply
        -> envoie la nouvelle version sur MinIO

MinIO est lu dans l'environnement : AWS_S3_ENDPOINT, AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY (et AWS_SESSION_TOKEN dans un VSCode).
turgot.alize n'est pas résolu par le DNS du cluster : le CSV passe par le proxy du lab
(ANNUAIRE_PROXY dans le pipeline, https_proxy dans un VSCode).

Le CSV (colonnes mail, affectation) liste les agents du service et leur bureau ; annuaire.parquet
est lu par les applications qui s'en servent.
Un CSV illisible, vide ou anormalement court est rejeté : l'ancien annuaire reste en place.
"""

import argparse
import http.client
import os
import ssl
import sys
from io import BytesIO, StringIO
from urllib.parse import urlsplit

import boto3
import pandas as pd
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

URL = "https://turgot.alize/csvd/annuaire.csv"
BUCKET = "db-sd2"
KEY = "annuaire.parquet"
COLUMNS = ["mail", "affectation"]
# Le proxy du lab filtre selon le User-Agent de la requête CONNECT : celui de curl passe
USER_AGENT = "curl/8.5.0"


def minio():
    endpoint = os.environ.get("AWS_S3_ENDPOINT")
    if not endpoint:
        sys.exit("AWS_S3_ENDPOINT n'est pas défini : MinIO injoignable, rien n'a été envoyé.")
    if "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    return boto3.client("s3", endpoint_url=endpoint, config=Config(connect_timeout=10, retries={"max_attempts": 3}))


def unreachable(error):
    sys.exit(f"MinIO inaccessible, rien n'a été envoyé :\n{error}\n"
             "Dans un VSCode, des identifiants expirés se renouvellent en redémarrant le service.")


def read_parquet(s3, key):
    """Le fichier de MinIO, None s'il n'existe pas. Toute autre erreur (identifiants, réseau) arrête le script."""
    try:
        body = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    except ClientError as error:
        if error.response["Error"]["Code"] == "NoSuchKey":
            return None
        unreachable(error)
    except BotoCoreError as error:
        unreachable(error)
    return pd.read_parquet(BytesIO(body))


def download(url, cacert, proxy):
    target = urlsplit(url)
    https = target.scheme == "https"
    # Le certificat de turgot.alize est signé par une AC interne absente du conteneur
    if cacert:
        context = ssl.create_default_context(cafile=cacert)
    else:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    connection = http.client.HTTPSConnection if https else http.client.HTTPConnection
    options = {"timeout": 60, "context": context} if https else {"timeout": 60}
    path = target.path or "/"
    if target.query:
        path += f"?{target.query}"
    try:
        if proxy and https:
            via = urlsplit(proxy if "://" in proxy else f"http://{proxy}")
            conn = connection(via.hostname, via.port or 3128, **options)
            conn.set_tunnel(target.hostname, target.port or 443, headers={"User-Agent": USER_AGENT})
        else:
            conn = connection(target.hostname, target.port, **options)
        conn.request("GET", path, headers={"User-Agent": USER_AGENT})
        response = conn.getresponse()
        status, body = response.status, response.read()
    except (OSError, http.client.HTTPException) as error:
        route = "par le proxy" if proxy and https else "sans proxy"
        sys.exit(f"Téléchargement impossible ({route}) : {error}")
    if status != 200:
        sys.exit(f"Le serveur a répondu {status} au lieu de 200 : annuaire inchangé.")
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return body.decode("iso-8859-1")


def parse(text):
    try:
        annuaire = pd.read_csv(StringIO(text), dtype=str, keep_default_na=False)
    except Exception as error:
        sys.exit(f"CSV illisible ({error}) : annuaire inchangé.")
    if list(annuaire.columns) != COLUMNS:
        sys.exit(f"Colonnes inattendues {list(annuaire.columns)[:5]} au lieu de {COLUMNS} : annuaire inchangé.")
    annuaire["mail"] = annuaire["mail"].str.strip().str.lower()
    annuaire["affectation"] = annuaire["affectation"].str.strip().str.upper()

    invalid = ~annuaire["mail"].str.fullmatch(r"[^@\s]+@[^@\s]+") | (annuaire["affectation"] == "")
    if invalid.any():
        # Numéros de ligne seulement : jamais d'adresses à l'écran
        lines = ", ".join(str(i + 2) for i in annuaire.index[invalid][:10])
        sys.exit(f"{invalid.sum()} ligne(s) invalide(s) dans le CSV (lignes {lines}) : annuaire inchangé.")
    duplicated = annuaire[annuaire.duplicated("mail", keep=False)].groupby("mail")["affectation"].nunique()
    if (duplicated > 1).any():
        sys.exit(f"{(duplicated > 1).sum()} adresse(s) rattachée(s) à plusieurs bureaux : annuaire inchangé.")
    return annuaire.drop_duplicates("mail").reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="envoyer le nouvel annuaire sur MinIO")
    parser.add_argument("--url", default=URL, help=f"adresse du CSV (défaut : {URL})")
    parser.add_argument("--proxy", default=os.environ.get("ANNUAIRE_PROXY") or os.environ.get("https_proxy"),
                        help="proxy HTTP vers le CSV (défaut : ANNUAIRE_PROXY, sinon https_proxy)")
    parser.add_argument("--cacert", help="certificat de l'AC interne (défaut : certificat non vérifié)")
    parser.add_argument("--min-rows", type=int, default=50, help="nombre minimal d'agents attendu (défaut : 50)")
    parser.add_argument("--force", action="store_true", help="accepter un annuaire beaucoup plus court que l'actuel")
    args = parser.parse_args()

    annuaire = parse(download(args.url, args.cacert, args.proxy))
    print(f"{len(annuaire)} agents, {annuaire['affectation'].nunique()} bureaux dans le CSV.")
    if len(annuaire) < args.min_rows:
        sys.exit(f"Moins de {args.min_rows} agents : annuaire inchangé.")

    s3 = minio()
    actuel = read_parquet(s3, KEY)
    if actuel is None:
        print("Pas encore d'annuaire sur MinIO : première synchronisation.")
    else:
        print(f"Annuaire actuel : {len(actuel)} agents.")
        if len(annuaire) < 0.7 * len(actuel) and not args.force:
            sys.exit("Le CSV a perdu plus de 30 % de ses agents : annuaire inchangé (--force pour passer outre).")

    updated = BytesIO()
    annuaire.to_parquet(updated, index=False)
    assert pd.read_parquet(BytesIO(updated.getvalue())).equals(annuaire)

    if not args.apply:
        print("\nSimulation : rien n'a été envoyé. Relance avec --apply pour envoyer le fichier.")
        return
    try:
        s3.put_object(Bucket=BUCKET, Key=KEY, Body=updated.getvalue())
    except (ClientError, BotoCoreError) as error:
        unreachable(error)
    print(f"\nEnvoyé sur {BUCKET}/{KEY}. ")


if __name__ == "__main__":
    main()
