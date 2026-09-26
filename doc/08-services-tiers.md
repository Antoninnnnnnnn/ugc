# 08 — Services tiers

Hôtes hors `www.ugc.fr` / `yoda.ugc.fr`, par volume de requêtes.

## Matomo self-host — `yoda.ugc.fr`

| Élément | Valeur |
|---|---|
| Container JS | `/js/container_BvdUBgTc.js` |
| Tracker | `POST /matomo.php` (Ping 204) |
| Site id | `2` |
| Heatmaps | `/plugins/HeatmapSessionRecording/configs.php?idsite=2` |
| Consentement | console `Tracking:disabled` après refus Hagreed |

Pages trackées : titre club fidélité, puis `UGC - Connexion` avec `urlref=club-fidelite.html`.

## Google Tag Manager / Ads / GA4

| Produit | ID |
|---|---|
| GTM | `GTM-NKL822` |
| GA4 | `G-29RY7XW3SW` (`region1.google-analytics.com/g/collect`) |
| Google Ads | `AW-11027272689` |
| Consent Mode | `gcs=G100`, `npa=1`, `pscdl=denied`, `gcd=13p3p3p2p5l1` |

Les collect `pagead2.googlesyndication.com/ccm/collect` et GA4 sont souvent **abortés** au changement de page (`net::ERR_ABORTED`) tout en ayant déjà un status 200/204.

## Facebook Pixel

| Champ | Valeur |
|---|---|
| Pixel | `468137016346103` |
| SDK | `connect.facebook.net` fbevents 2.9.408 |
| Events | `PageView`, `SubscribedButtonClick`, `InputData` |
| Clicks trackés | refus Hagreed, CTA « Rejoindre… », onglet « Je crée un compte » |
| Advanced matching | hash `zp` (zip) même sans formulaire CP |

Beacons `www.facebook.com/tr/` en GET image et POST document (iframes `fb…`).

Endpoint parallèle AWS :

`https://m6-211026f8a25b42c08fc190458268b30e.ecs.us-east-2.on.aws/events?cee=no`

JSON `{ event_name, fb.pixel_id, fb.fbp, website_context }` — plusieurs POST abortés.

## Hagreed CMP — `api.hagreed.com`

Voir [09-consentement-hagreed.md](09-consentement-hagreed.md).

## Batch — notifications web

| Champ | Valeur |
|---|---|
| Bootstrap | `https://via.batch.com/v4/bootstrap.min.js` |
| SDK | `via.batch.com/4.4.0/sdk.min.js` |
| Manifest versions | latest major 4 = `4.4.0`, major 5 = `5.0.0` |
| API events | `POST https://ws.batch.com/web/4.4.0/ev/{API_KEY}` |
| SW | `https://www.ugc.fr/batchsdk-worker-loader.js` |

Payload observé : événements `_PROFILE_DATA_CHANGED` (`device_language=fr-FR`, `device_timezone=Europe/Paris`), `data_collection.geoip=false`, `profile_probation=true`, `cus/ure/ula/upv=null`.

Le timeout CDP qui **tue la capture** est l’attache de ce service worker.

## Smart Tribune

`https://assets.app.smart-tribune.com/ugc/PUSH/{push.main.js,push.js,push.css}` — widget aide / FAQ. Pas d’appel API métier observé.

## Sentry

Uniquement `login.html`. Ingest 429 quota. Replay activé (`sampled: session`). Voir [06-authentification.md](06-authentification.md).

## Friendly Captcha

`global.frcapi.com` — voir [06-authentification.md](06-authentification.md).

## Affiliation

Dealabs + Digidip : voir [02-parcours-utilisateur.md](02-parcours-utilisateur.md). Pas de cookie UGC d’affiliation.

## CDN divers

- `cdnjs.cloudflare.com` — Font Awesome 4.7
- `cdn.jsdelivr.net` — Friendly Captcha SDK

## Identifiants marketing à retenir

```
GTM-NKL822
G-29RY7XW3SW
AW-11027272689
Facebook Pixel 468137016346103
Matomo idsite=2 (yoda.ugc.fr)
Hagreed consent category: hagreed:prehome_ugc
Friendly Captcha sitekey: FCMR306TFOLA6D49
```
