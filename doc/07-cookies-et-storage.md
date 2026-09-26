# 07 — Cookies et Web Storage

État final reconstruit depuis le flux d’événements (`snapshots/cookies_final.json`, `dom_storage_final.json`). Les **valeurs** de session ne sont pas recopiées ici ; elles sont dans la capture brute.

## Cookies finaux (11)

### Dealabs (chaîne d’entrée, hors UGC)

| Nom | Domain | HttpOnly | Secure | SameSite | Rôle |
|---|---|---|---|---|---|
| `pepper_session` | `www.dealabs.com` | oui | oui | — | Session Pepper (~35 min) |
| `f_v` | `www.dealabs.com` | non | oui | — | Visitor ID 1 an |
| `u_l` | `www.dealabs.com` | oui | oui | — | Flag court (~15 min) |
| `xsrf_t` | `www.dealabs.com` | non | oui | Strict | CSRF Dealabs |
| `lcl` | `www.dealabs.com` | oui | oui | — | Thread `3417894`, TTL 60 s |

Ils ne sont **pas** envoyés à `ugc.fr`.

### UGC

| Nom | Domain | HttpOnly | Secure | SameSite | Rôle |
|---|---|---|---|---|---|
| `JSESSIONID` | `www.ugc.fr` | **oui** | **oui** | Lax | Session Java, posé sur `login.html` uniquement |
| `hagreedId` | `.ugc.fr` | non | **non** | — | ID consentement CMP (~6 mois) |
| `hagreedCookies` | `.ugc.fr` | non | **non** | — | Liste consentie : `[]` après refus |
| `_pk_id.2.931e` | `.ugc.fr` | non | non | Lax | Matomo visitor (site id 2) |
| `_pk_ses.2.931e` | `.ugc.fr` | non | non | Lax | Matomo session |
| `_fbp` | `.ugc.fr` | non | non | Lax | Facebook browser pixel |

Points notables :

- `hagreedId` / `hagreedCookies` sont **non Secure** alors que le site est 100 % HTTPS.
- Matomo et `_fbp` sont posés **avant** le clic « Continuer sans accepter » (scripts déjà injectés). Après refus, GTM loggue `Tracking:disabled` et GA part avec `npa=1` / `pscdl=denied`, mais les cookies `_pk_*` et `_fbp` restent.
- Pas de cookie `remember-me` (checkbox non utilisée).
- Pas de cookie d’auth métier autre que `JSESSIONID`.

## Ordre de pose

1. Dealabs `set-cookie` sur le 302 initial
2. `hagreedId` dès le check-license Hagreed
3. `_pk_id`, `_pk_ses`, `_fbp` au chargement GTM/Matomo/Facebook
4. `hagreedCookies=[]` au clic refus (`frameNavigated`)
5. `JSESSIONID` au GET `login.html`

## localStorage `https://www.ugc.fr`

| Clé | Valeur observée | Origine |
|---|---|---|
| `i18nextLng` | `fr` | i18next (test write `i18next.translate.boo` puis delete) |
| `lastExternalReferrer` | `empty` | Facebook Pixel |
| `lastExternalReferrerTime` | epoch ms | Facebook Pixel |

Hagreed / i18next font un probe `localStorage['~~~']='!'` puis suppression (test de disponibilité).

## sessionStorage `https://www.ugc.fr`

| Clé | Rôle |
|---|---|
| `frc_sid` | Session Friendly Captcha |
| `frc_sc` | Compteur d’iframes FRC (1 → 3) |
| `sentryReplaySession` | Replay Sentry (id, started, sampled=session) |

`sentryReplaySession` n’apparaît que sur login.

## Storage Friendly Captcha (partitioned)

Origine `https://global.frcapi.com` avec storage key `https://global.frcapi.com/^0https://ugc.fr` : tests `frcv2_test` / `frc_icg` ajoutés puis retirés. État final vide.

## IndexedDB / Cache Storage

Aucun dump (`idbEntries: 0`, `cacheEntries: 0`). Le SW Batch est attaché mais la capture meurt avant un dump utile.

## Console

Deux logs identiques : **`Tracking:disabled`**, stack dans `yoda.ugc.fr/js/container_BvdUBgTc.js` (container Matomo Tag Manager). Cohérent avec le refus CMP.
