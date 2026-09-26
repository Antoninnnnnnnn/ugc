# 01 — Métadonnées de capture

## Identité

| Champ | Valeur |
|---|---|
| Dossier | `session_20260926_222300_798_20272_f3ab` |
| Logger | Chrome Network Logger **3.1.1** |
| Schéma | `schemaVersion: 3` |
| Début | 2026-09-26T22:23:00.802+02:00 |
| Fin | 2026-09-26T22:23:27.546+02:00 |
| Durée utile page | ~12 s d’interaction (22:23:10 → 22:23:20) |
| Statut | **`error`** |
| Raison d’arrêt | `error:RuntimeError` — health check `Network.enable` |

## Configuration du logger

```json
{
  "bodyMode": "api",
  "sensitiveMode": "raw",
  "maxBodyBytes": 33554432,
  "maxSessionBodyBytes": 2147483648,
  "captureInteractions": true,
  "captureClipboard": false,
  "captureConsole": true,
  "captureStorage": true
}
```

- `bodyMode: api` : corps conservés pour Document / XHR / Fetch classés API.
- `sensitiveMode: raw` : cookies, CSRF, e-mails tapés, tokens frontend **non rédigés** dans la capture brute.
- Interactions, console et storage activés. Presse-papiers désactivé.

## Navigateur

| Champ | Valeur |
|---|---|
| Chrome | 153.0.8010.53 (install système) |
| CDP | protocol 1.3 |
| UA | Windows 10/11, `fr-FR` |
| Viewport | 1536×864 |
| Proxy | désactivé |
| Profil | profil isolé `capture_profile` (pas le Chrome utilisateur) |

## Statistiques

| Métrique | Valeur |
|---|---|
| Requêtes | 175 |
| Réponses | 172 |
| Classées API | 46 |
| Corps stockés | 37 (34 uniques, ~992 Ko) |
| Redirections | 3 (chaîne Dealabs) |
| Failures réseau | 9 (`net::ERR_ABORTED`, principalement tracking annulé) |
| HTTP 4xx/5xx | 2 × **429** Sentry |
| Événements utilisateur | 23 |
| Changements cookies | 16 |
| Changements storage | 42 |
| Flushes storage | 37 |
| Erreurs protocole | 2 (timeouts requis) |
| Incomplete flushed | 9 |
| Interception bypassed | 1 |
| WebSocket / SSE | 0 |

Répartition par type CDP :

| Type | Nb |
|---|---|
| Script | 83 |
| Fetch | 21 |
| Stylesheet | 18 |
| Image | 16 |
| Document | 11 |
| XHR | 11 |
| Font | 8 |
| Manifest | 2 |
| Ping | 2 |
| Other | 2 |
| Preflight | 1 |

## Avertissements du manifest

```
Required CDP command timed out: Network.enable
Capture terminated with RuntimeError: Capture health check failed: Network.enable
```

Le timeout porte sur la session CDP du **service worker Batch**
`https://www.ugc.fr/batchsdk-worker-loader.js` (`sessionId` `F80781EA…`).
`Runtime.enable` timeout au même moment.

La capture n’est **pas complète** au sens du schéma v3. Les pages `club-fidelite.html` et `login.html` sont néanmoins bien présentes, avec corps HTML, XHR first-party, cookies et interactions.

## Arborescence utile

```
session_…_f3ab/
  manifest.json
  timeline.jsonl
  network/requests.jsonl          ← source réseau canonique
  network/bodies/*.html.gz|json.gz
  interactions/events.jsonl
  browser/{navigations,targets,console,log,protocol_errors}.jsonl
  storage/{cookie_changes,dom_storage_events,page_flushes}.jsonl
  snapshots/{cookies_final,dom_storage_final}.json
  reports/{summary.txt,stats.txt,requests.csv,interactions.html}
```

## Extensions présentes dans le profil de capture

Pas du site UGC : le profil logger embarque des service workers d’extensions Chrome
(`chrome-extension://fignfifoniblkonapihmkfakmlgkbkcf` TTS, Google Docs Offline).
Ils n’interviennent pas dans le parcours UGC.
