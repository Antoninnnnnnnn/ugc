# 09 — Consentement Hagreed

CMP française **Hagreed**, package `Pro - SDK Node`, licence liée à `www.ugc.fr`.

## Intégration front

```html
<script src="./lib/hagreed/js/hagreed.js?version=14.38.0-rc4"></script>
<script id="hagreedinitjs"
        src="./lib/hagreed/js/hagreed.init_fr.js?version=14.38.0-rc4"
        data-token="…licence site…"></script>
```

Le token de licence est **public** (attribut HTML). Hagreed le revalide à chaque page.

Bannière : `#hagreed`. Footer : lien `#open-hagreed` « Cookies ».

Catégorie de script gated :

```html
<script type="hagreed/javascript" data-consent="hagreed:prehome_ugc">
  $(document).ready(function() {
    getAdvertising('INTERSTITIEL', 'body');
  });
</script>
```

## API `https://api.hagreed.com`

### Check licence

```
POST /api/check-license
multipart/form-data
  token={licence}
  package_type=pro_sdk_node
```

Réponse :

```json
{
  "status": "OK",
  "response": {
    "site_url": "www.ugc.fr",
    "package_name": "Pro - SDK Node",
    "package_type": "pro_sdk_node",
    "package_version": "0.1.0",
    "status": "enabled",
    "customer_id": "2015a88c-2d36-4763-b372-cf09af4f4b8a",
    "date_created_utc": "2023-12-05 …"
  },
  "message": "License OK!"
}
```

Appelé au chargement de **chaque** page (club + login).

### Hits CMP

```
POST /api/hit
multipart/form-data
  token={licence}
  type={CN_SHOW|CN_DECLINE|…}
  lang=fr
```

| Heure | Type | Signification |
|---|---|---|
| 22:23:11.810 | `CN_SHOW` | Affichage de la bannière (id hit `479100f6-…`) |
| 22:23:13.843 | `CN_DECLINE` | Refus total (id hit `4bb5517c-…`) |

Le bouton cliqué :

```html
<button class="hagreed__continue hagreed-validate"
        aria-label="Continuer sans accepter"
        data-type="decline_all">
  Continuer sans accepter →
</button>
```

Pas de `CN_ACCEPT` dans la session.

## Cookies CMP

Après refus : `hagreedCookies=[]`. L’ID `hagreedId` reste (suivi du consentement, pas des vendors).

Les tags GTM/Matomo/Facebook **ont déjà tourné** entre `CN_SHOW` et `CN_DECLINE` (~2,6 s). D’où `_fbp` / `_pk_*` déjà posés, puis `Tracking:disabled` et GA en mode non personnalisé.

## Effet observé du refus

- Console : `Tracking:disabled`
- GA4 : `npa=1`, `pscdl=denied`, `gcs=G100`
- Facebook Pixel : `coo=false`, `cdl=API_unavailable`
- Batch : `data_collection.geoip=false`
- Interstitiel pub Hagreed-gated : non injecté (réponses pub vides de toute façon)
