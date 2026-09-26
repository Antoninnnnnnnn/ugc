# UGC — comptes fidélité

Client HTTP (sans navigateur) qui crée un compte UGC, l’active, se connecte, et l’inscrit au programme fidélité.

Un compte prend environ une minute. Le succès, c’est l’adhésion acceptée sur `fidelite.ugc.fr`.

## Offre (23–29 septembre 2026)

- **100 points** à l’adhésion, plus **100 points le 8 octobre 2026** si le compte n’a pas été au programme fidélité entre le 1er janvier et le 22 septembre 2026, et n’a jamais déjà reçu de points ou une place offerte pour une adhésion précédente.
- **200 points = une place de cinéma le mardi.**
- Les points sont valables **9 mois**.

## Installation

Python 3.11 ou plus.

```bash
python -m pip install -r requirements.txt
copy .env.example .env
```

Remplis `.env` :

| Variable | Rôle |
|---|---|
| `CATCHALL_DOMAINS` | Optionnel. Domaines catch-all, séparés par des virgules. Vide : le premier compte utilise `IMAP_USER`, puis le script demande si les suivants doivent être des alias Gmail avec des points (`prenom.nom@gmail.com`) |
| `IMAP_USER` | Adresse Gmail |
| `IMAP_APP_PASSWORD` | Mot de passe d’application Gmail (16 caractères, les espaces sont ignorés) |
| `CAPTCHA_API_KEY` | Clé CapMonster Cloud |

Le captcha du site est Friendly Captcha **v2**. CapSolver ne produit que des jetons v1, que UGC refuse. Le fournisseur attendu est CapMonster (`CAPTCHA_PROVIDER=capmonster`).

## Proxies

Fichier `proxy.txt`, une ligne par proxy :

```
http://host:port:utilisateur:motdepasse
```

`USE_PROXY=auto` et `USE_IMAP=auto` (défaut) : le proxy est utilisé s’il y a des lignes dans `proxy.txt`, l’IMAP est utilisé si le mot de passe est renseigné. `0` force la désactivation.

Sans proxy, la connexion part en direct. Sans IMAP, le script s’arrête après l’envoi du mail et demande de coller le lien d’activation.

## Lancer

```bash
py main.py
```

| Choix | Action |
|---|---|
| 1 | Créer des comptes. Avec l’IMAP, plusieurs en parallèle (5 maximum). Sans IMAP, un par un, le temps de coller le lien |
| 2 | Voir les comptes (e-mail, mot de passe, points). Les échecs sont masqués, sauf si on demande à les voir |
| 3 | Exporter les comptes OK dans `accounts.csv` |
| 4 | Finir l’adhésion d’un compte déjà activé mais pas encore fidélité |
| 5 | Lire les derniers mails reçus |
| 6 | Vérifier proxies, solde captcha et IMAP |
| 7 | Couper le proxy ou l’IMAP pour cette session |

Les mêmes actions en ligne de commande :

```bash
py main.py create 10 -t 3    # 10 comptes, 3 en parallèle
py main.py create 1 --no-proxy --no-imap
py main.py list              # ajouter -a pour voir les échecs
py main.py export
py main.py check
```

Chaque compte consomme deux captchas (inscription, puis connexion).

## Où sont les comptes

`runs/<date>_<id>/credentials.json` est écrit avant la première requête : e-mail, mot de passe, nom, date de naissance, code postal. `result.json` dit jusqu’où le parcours est allé.

`accounts.csv` (séparateur `;`) reprend les comptes OK : e-mail, mot de passe, points, statut, identifiant du run. Il est réécrit après chaque compte. Il se régénère depuis `runs/` : ne supprime pas ce dossier.

Les mots de passe sont en clair. Ces fichiers ne sont pas dans git.

## Ce qui ne part pas sur GitHub

`.env`, `proxy.txt`, `runs/`, `accounts.csv`.

L’analyse de la capture réseau qui a servi à écrire le client est dans [doc/README.md](doc/README.md).
