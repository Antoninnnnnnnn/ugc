# 03 — Architecture technique

## Hébergement

`www.ugc.fr` est derrière un **Google Cloud Load Balancer** :

| En-tête / indice | Valeur |
|---|---|
| `server` | `Jetty(10.0.25)` |
| `via` | `1.1 google` |
| IP observée | `35.244.207.4` |
| TLS | 1.3, `X25519`, AES-128-GCM |
| Certificat | `ugc.fr` + `*.ugc.fr`, émetteur WR3 |
| HTTP | HTTP/2 (`h2`), `alt-svc: h3` annoncé |
| Locale applicative | `ugc-locale: fr_FR` |
| Build | `ugc-build-version: 4ff228808df8806d71d0b24a874e27fb` |

Le dataLayer first-party remonte `remote_addr` en **`35.191.x.x`** (plage Google). L’IP client réelle n’est pas celle vue par l’appli derrière le LB, ou le champ reflète le hop Google.

`environment` dataLayer : **`production`**.

## Stack applicative

Application **Java classique**, pas un SPA.

| Couche | Techno |
|---|---|
| Serveur HTTP | Eclipse Jetty 10.0.25 |
| MVC | Apache **Struts 2** (actions `*Action` / `*Action!method`) |
| Plugins UI | **struts2-jquery 4.0.7** (`s2j=4.0.7`) |
| Auth | **Spring Security** (`/j_spring_security_check`, `_csrf`) |
| Session | Cookie `JSESSIONID` (valeur UUID base64) |
| JS | jQuery **3.4.1**, jQuery UI, Bootstrap, Popper, Underscore |
| CSS | `application.css?version=14.38.0-rc4` |
| i18n datepicker | `datepicker-fr.min.js` |

Convention d’URL Struts 2 observée :

```
/{ActionName}                  → execute()
/{ActionName}.action
/{ActionName}!{method}
/{ActionName}!{method}.action
```

Exemples : `analyticsAjaxAction!retrieveDataLayerInformations`,
`advertisingCampaignAjaxAction!getAdvertisingCampaign`,
`monCompteInscriptionAction!validationEmail.action`.

## Cache

| Page | Cache-Control | Implication |
|---|---|---|
| `/club-fidelite.html` | `public, max-age=1800` (répété 6×) | Page marketing CDN-able, HTML figé 30 min |
| `/login.html` | `no-cache, no-store, must-revalidate` | Page d’auth : CSRF + session, jamais cachée |
| Assets `?version=14.38.0-rc4` | 304 au 2ᵉ chargement | Cache navigateur par query de version |
| Struts JS | 304 au 2ᵉ chargement | Idem |

Le HTML de `club-fidelite.html` fait 48 346 octets. `login.html` fait 57 247 octets.

## Front partagé

Les deux pages chargent le même socle :

- Header / recherche film-cinéma (`searchAjaxAction.action`, `searchAction.action`)
- Hagreed CMP
- Smart Tribune (FAQ / push)
- Batch SDK (notifications web) + service worker `/batchsdk-worker-loader.js`
- GTM `GTM-NKL822` + Matomo self-host `yoda.ugc.fr`
- Campagnes pub `advertisingCampaignAjaxAction`
- Footer apps (App Store / Google Play) et Mag UGC septembre 2026

`login.html` ajoute en plus :

- Sentry browser 7.120.4 (loader lazy `js.sentry-cdn.com`)
- Friendly Captcha SDK 0.1.31
- Formulaires Spring Security / inscription / forgot / resend

## Sous-domaines UGC vus

| Hôte | Rôle |
|---|---|
| `www.ugc.fr` | Site principal |
| `yoda.ugc.fr` | Matomo (container + heatmap + `matomo.php`) |
| `fidelite.ugc.fr` | Catalogue cadeaux (lien HTML, **non visité**) |
| `api.hagreed.com` | CMP (tiers, pas UGC) |

## IDs de pages CMS (attributs `data-page` / champs `page`)

| ID | Contexte |
|---|---|
| `30002` | `login.html` — campagnes `PLAYER_FOOTER` |
| `30004` | Formulaires de recherche header (toutes pages) |
| `30058` | Funnel inscription (`inscription_form` / `redirect_form`) |
| `32073` | `club-fidelite.html` — campagnes `PLAYER_FOOTER` |

## Entité légale (bloc Ajax login)

`GET /blocAjaxAction.action?code=MentionsIdentification` retourne le responsable de traitement :

**UGC CINÉ CITÉ** — SAS, 24 avenue Charles de Gaulle, 92200 Neuilly-sur-Seine, RCS Nanterre 347.806.002, capital 112 404 145,92 €.

Conservation : 3 ans après suppression de compte ou 3 ans d’inactivité. Droits Informatique et Libertés via Service clientèle ou `/contact.html`.
