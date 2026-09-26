# 05 — API first-party

Base : `https://www.ugc.fr`. Toutes les XHR observées sont same-origin, cookies automatiques, pas d’en-tête `Authorization`.

Le site n’expose **pas** d’API REST JSON publique de type `/api/v1`. C’est un backend Struts 2 : HTML pages + actions Ajax qui renvoient JSON **ou** fragments HTML.

## Inventaire observé

| Méthode | Endpoint | Page | Réponse | Corps req | Notes |
|---|---|---|---|---|---|
| POST | `/analyticsAjaxAction!retrieveDataLayerInformations` | les 2 | JSON | `filmId=&cinemaId=` | DataLayer analytics / e-commerce |
| GET | `/maintenanceAjaxAction` | les 2 | HTML vide | — | Bandeau maintenance (vide ici) |
| GET | `/advertisingCampaignAjaxAction!getAdvertisingCampaign?displayWidth={w}&type=HEADER` | les 2 | HTML vide | — | Pub header |
| GET | `/advertisingCampaignAjaxAction!getAdvertisingCampaign?displayWidth={w}&type=PLAYER_FOOTER&pageId={id}` | les 2 | HTML vide | — | Pub footer player |
| GET | `/blocAjaxAction.action?code=MentionsIdentification` | login | HTML | — | Mentions RGPD sous le formulaire |

Non appelés mais présents dans le HTML :

| Méthode | Endpoint | Rôle |
|---|---|---|
| POST | `/searchAjaxAction.action` | Autocomplete recherche |
| POST | `/searchAction.action` | Soumission recherche |
| POST | `/j_spring_security_check` | Login Spring Security |
| POST | `/monCompteInscriptionAction.action` | Redirect inscription (form hidden) |
| POST | `/monCompteInscriptionAction!validationEmail.action` | Validation e-mail (Ajax Struts2-jQuery) |
| POST | `/forgotAction.action` | Mot de passe oublié |
| POST | `/resendActivationEmailAction.action` | Renvoi mail d’activation |

## `analyticsAjaxAction!retrieveDataLayerInformations`

```
POST /analyticsAjaxAction!retrieveDataLayerInformations
Content-Type: application/x-www-form-urlencoded
Body: filmId=&cinemaId=
```

Réponse `application/json;charset=utf-8` : `{ "dataLayer": [ { ... } ] }`.

Champs utiles (état **anonyme**, session non loguée) :

| Champ | Club fidélité | Login |
|---|---|---|
| `environment` | `production` | `production` |
| `has_user_info` | `false` | `false` |
| `has_just_logged_in` | `false` | `false` |
| `is_fid_user` | `false` | `false` |
| `fid_points` | `0` | `0` |
| `userId` | `null` | hash hex 32 car. |
| `first_name` | `null` | `null` |
| `cinemas_favoris` | `null` | `null` |
| `watch_list` | `null` | `null` |
| `display_for_apps` | `false` | `false` |
| `film_with_programmation` | `true` | `true` |

Le schéma couvre aussi tout le tunnel **réservation** et **achat de carte** (totaux, promo, 3D, sièges, `reservation_use_fidelity_card`, etc.). Tous ces champs sont `null` / `false` ici : la page de fidélité/login n’est pas un tunnel d’achat.

Le `userId` hashé apparaît seulement sur `login.html` (après `JSESSIONID`). Sur la page marketing cachée, `userId` reste `null`.

Le front fusionne cette réponse dans `dataLayer` puis pousse GTM.

## Campagnes pub

```
GET /advertisingCampaignAjaxAction!getAdvertisingCampaign
    ?displayWidth={1036|1536}
    &type={HEADER|PLAYER_FOOTER|INTERSTITIEL}
    [&pageId={30002|32073}]
```

`displayWidth` suit le viewport (1036 sur club, 1536 sur login). Les réponses capturées sont des fragments HTML **vides** (campagnes absentes ou filtrées).

Un interstitiel est prévu au consentement Hagreed `prehome_ugc` :

```javascript
getAdvertising('INTERSTITIEL', 'body');
```

Non déclenché visiblement (réponse vide / CMP refusé).

## Maintenance

`GET /maintenanceAjaxAction` → HTML vide. Le script `js/pages/maintenance.js` injecterait un bandeau si le fragment n’est pas vide.

## Blocs CMS

```
GET /blocAjaxAction.action?code={CodeBloc}
```

Code observé : `MentionsIdentification`. Pattern générique de fragments HTML réutilisables.

## Contrat d’erreur

Aucune 4xx/5xx first-party dans la session. Les 429 concernent uniquement Sentry. Les « FAIL » du summary sont des `net::ERR_ABORTED` sur des beacons tiers (GTM/GA/Facebook/FRC ping) annulés au changement de page ou au refus de cookies — pas des pannes UGC.
