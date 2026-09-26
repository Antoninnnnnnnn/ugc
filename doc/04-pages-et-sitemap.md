# 04 — Pages, sitemap et IDs CMS

Seules deux pages UGC sont chargées. Le header/footer HTML expose néanmoins un **sitemap marketing** complet.

## Pages visitées

### `GET /club-fidelite.html`

- Titre : *Le Programme fidélité UGC : plus simple, plus généreux*
- Section `#generic`, blocs `#title-detail-club`, `#how-to-join-club`
- Campagne visuelle : `boost-fidelite-septembre-2026_1114x{225,356}.jpg`
- `data-page="32073"`
- Cache 1800 s, pas de `JSESSIONID`

Contenu métier observé :

- Adhésion → 100 points offerts (offre boost 23–29 sept. 2026 + 100 points le 8 oct. sous conditions)
- 10 % confiserie membres fidélité, 20 % abonnés UGC Illimité
- Points : achats places, cartes 5 places, confiserie, notation films (+10), 1er cinéma favori (+5), parrainage, paliers 500/1000/2000, bonus Illimité 5 ans / 10 ans, +10 pts/mois Illimité, anniversaire
- QR Code fidélité à présenter en cinéma
- Catalogue cadeaux : `https://fidelite.ugc.fr/catalogue-cadeaux.html` (sous-domaine dédié)

Parcours d’adhésion (3 étapes dans la page) :

1. Créer / se connecter à son Compte
2. S’inscrire au Programme (rubrique « Mon Programme fidélité ») et récupérer la carte dématérialisée
3. Présenter le QR Code à chaque visite

Le CTA de la session court-circuite l’étape 2 : il envoie directement sur `login.html`.

### `GET /login.html`

- Titre : *UGC - Connexion*
- Description : saisie e-mail / mot de passe, ou création de compte
- `data-page="30002"`
- `Cache-Control: no-cache, no-store, must-revalidate`
- Pose `JSESSIONID`
- Charge Sentry + Friendly Captcha
- Charge `GET /blocAjaxAction.action?code=MentionsIdentification` dans `#mentionsDiv`

## Sitemap (liens header / footer)

Chemins relatifs sur `www.ugc.fr` :

| URL | Zone |
|---|---|
| `films.html` | Header |
| `films.html?filter=ugcFamily` | Header |
| `cinemas.html` | Header |
| `profil.html` | Compte (icône) |
| `login.html` | Auth |
| `les-offres-ugc-illimite.html` | Offres |
| `les-offres-ugc.html` | Offres |
| `passculture.html` / `passCulture.html` | Offres (deux casses) |
| `labels-et-selections.html` | Éditorial |
| `evenements.html` | Éditorial |
| `vivalopera.html` | Éditorial |
| `news.html` | Éditorial |
| `le-mag-by-ugc.html` | Mag |
| `club-fidelite.html` | Fidélité (page courante) |
| `bareme-points.html` | Fidélité |
| `comptoir.html` | Confiserie |
| `note-certifiee-ugc.html` | Notation films |
| `aide.html` | Footer |
| `contact.html` | Footer |
| `politique_confidentialite.html` | Footer |
| `conditions-MonCompte.html` | Footer |
| `mentionslegales.html` | Footer |
| `/accessibilite.html` | Footer |
| `/chartespectateurs.html` | Footer |

Hors `www` :

- `https://fidelite.ugc.fr/catalogue-cadeaux.html`

Réseaux sociaux footer : Facebook, Twitter/X, Instagram, TikTok, YouTube, LinkedIn (`UGCcinemas` / `ugc`).

## Recherche globale

Présente sur les deux pages :

| Formulaire | Méthode | Action | Champs |
|---|---|---|---|
| `#previewSearchForm` | POST Ajax | `/searchAjaxAction.action` | `page=30004`, `searchKey` |
| `#enterSearchForm` | POST | `/searchAction.action` | `page=30004`, `searchKey` |

L’autocomplete publie l’événement jQuery `executeSearch` au `keyup`. **Non exercé** dans la session.

## Assets first-party notables

- Fonts : `UniformExtraCondensed-{Regular,Medium,Bold}.woff2`, icônes `UGCIcons.ttf`
- Logo : `logo-ugc-cyan-blanc.png`
- Mag septembre 2026, visuel footer mobile v12
- PWA-like : `/assets/favicon/manifest.json`
- JS métier : `main.js`, `alteis.js`, `header.js`, `apps.js`, `validation-utils.js`, `trailer.js`, `dateselect.js`, `maintenance.js`, `advertising-campaign.js`, `generic/generic.js` (club uniquement)
