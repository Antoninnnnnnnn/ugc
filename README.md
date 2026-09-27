# UGC — comptes fidélité

Client HTTP (sans navigateur) qui crée un compte UGC, l’active, se connecte, et l’inscrit au programme fidélité.

Chaque compte prend environ une minute. L’opération est réussie lorsque `fidelite.ugc.fr` accepte l’adhésion.

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
| `CATCHALL_DOMAINS` | Optionnel. Domaines catch-all, séparés par des virgules. Vide : le premier compte reprend `MAIL_USER`. Avec Gmail, le script peut ensuite proposer des alias (points dans la partie locale) |
| `MAIL_USER` | Adresse de la boîte qui reçoit les mails d’activation |
| `MAIL_PASSWORD` | Mot de passe, ou mot de passe d’application (Gmail, Outlook). Les espaces sont ignorés |
| `MAIL_PROTOCOL` | `auto`, `imap`, `pop3` ou `manual`. `auto` : IMAP si les identifiants sont remplis, sinon demande des adresses au lancement |
| `CAPTCHA_API_KEY` | Clé CapMonster Cloud |

Le captcha du site est Friendly Captcha **v2**. CapSolver ne produit que des jetons v1, que UGC refuse. Le fournisseur attendu est CapMonster (`CAPTCHA_PROVIDER=capmonster`).

## Proxies

Fichier `proxy.txt`, une ligne par proxy :

```
http://host:port:utilisateur:motdepasse
```

`USE_PROXY=auto` : le proxy est utilisé s’il y a des lignes dans `proxy.txt`. `0` force la connexion directe.

L’hôte mail est déduit de l’adresse : Gmail, Outlook, Hotmail, Yahoo, iCloud, GMX, Orange, Free, La Poste, SFR. Pour un autre fournisseur, indique `MAIL_HOST`. Le menu (choix 7) passe d’IMAP à POP3, puis à la saisie manuelle.

Si `MAIL_USER` et `MAIL_PASSWORD` sont vides, `py main.py` demande tout de suite les adresses à coller, puis le lien d’activation de chacune. Une ligne vide revient au menu.

## Lancer

```bash
py main.py
```

| Choix | Action |
|---|---|
| 1 | Créer des comptes. En IMAP ou POP3, plusieurs en parallèle. Sans lecture du mail, coller les adresses, puis le lien de chacune, un compte à la fois |
| 2 | Voir les comptes (e-mail, mot de passe, points). Les échecs sont masqués par défaut |
| 3 | Exporter les comptes OK dans `accounts.csv` |
| 4 | Terminer l’adhésion d’un compte déjà activé, pas encore inscrit au programme |
| 5 | Lire les derniers mails reçus |
| 6 | Vérifier les proxies, le solde captcha et la connexion à la boîte mail |
| 7 | Désactiver le proxy, ou changer le protocole mail, pour la session en cours |

Les mêmes actions en ligne de commande :

```bash
py main.py create 10 -t 3    # 10 comptes, 3 en parallèle
py main.py create --no-imap          # demande les adresses, puis chaque lien
py main.py list              # ajouter -a pour voir les échecs
py main.py export
py main.py check
```

Chaque compte consomme deux captchas (inscription, puis connexion).

## Où sont les comptes

`runs/<date>_<id>/credentials.json` est écrit avant la première requête : e-mail, mot de passe, nom, date de naissance, code postal. `result.json` enregistre l’étape atteinte, y compris en cas d’échec.

`accounts.csv` (séparateur `;`) reprend les comptes OK : e-mail, mot de passe, points, statut, identifiant du run. Il est réécrit après chaque compte, à partir de `runs/`. Ne supprime pas ce dossier.

Les mots de passe sont en clair. Ces fichiers ne sont pas dans git.

## Ce qui ne part pas sur GitHub

`.env`, `proxy.txt`, `runs/`, `accounts.csv`.

L’analyse de la capture réseau qui a servi à écrire le client est dans [doc/README.md](doc/README.md).
