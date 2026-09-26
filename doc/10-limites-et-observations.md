# 10 — Limites de la capture et observations

## Limites

1. **Capture `status: error`**. Timeout CDP `Network.enable` / `Runtime.enable` sur le service worker Batch. Ne pas traiter le dossier comme une session complète au sens du schéma v3.
2. **`bodyMode: api`**. Les JS/CSS/images n’ont en général pas de corps stockés. L’analyse du JS métier (`main.js`, `alteis.js`, `header.js`) n’est pas possible depuis cette session seule.
3. **Parcours court**. Pas de login réussi, pas d’inscription complète, pas de compte fidélité, pas de QR, pas de catalogue `fidelite.ugc.fr`, pas de résa / paiement.
4. **9 requêtes `incompleteFlushed`**. Beacons abortés au unload + attache SW ratée.
5. **1 `interceptionBypassed`**. Au moins une requête a contourné l’interception Fetch CDP.
6. **Iframes Facebook / FRC**. Plusieurs attach/detach rapides ; des commandes `quiesce` échouent (`Session with given id not found`).
7. **Profil logger neuf**. Pas d’historique compte, pas de cookies UGC préexistants, extensions du profil de capture (TTS, Docs Offline) sans lien avec UGC.
8. **Secrets en clair dans la brute**. `sensitiveMode: raw` : CSRF, `JSESSIONID`, e-mail partiel, tokens Dealabs. Cette doc ne les recopie pas.

## Observations techniques

### Auth / sécurité

- Login = Spring Security classique + CSRF + Friendly Captcha (démarrage au submit).
- `login.html` est `no-store` ; `club-fidelite.html` est CDN 30 min — séparation nette page publique / page session.
- `JSESSIONID` : HttpOnly + Secure + Lax. Correct.
- Cookies Hagreed **sans flag Secure**.
- Formulaire d’**inscription e-mail** et **resend activation** : pas de CSRF ni captcha dans le HTML capturé. À confirmer côté serveur (filtre Spring global possible).
- `remember-me` existe ; non testé.
- Mot de passe : `autocomplete=off` + toggle œil SVG.

### Produit fidélité

- L’adhésion réelle n’est pas le CTA `login.html` : le copy parle d’une rubrique **« Mon Programme fidélité »** dans le compte, carte dématérialisée + QR.
- Catalogue cadeaux isolé sur **`fidelite.ugc.fr`**.
- Offre « boost » septembre 2026 : 100 pts à l’adhésion + 100 pts le 8 octobre sous conditions (compte inactif fidélité depuis le 01/01/2026, pas d’e-mail jetable, 1 crédit / personne).
- DataLayer déjà prêt pour `is_fid_user` / `fid_points` / `reservation_use_fidelity_card`.

### Tracking vs consentement

- Fenêtre ~2,6 s entre affichage CMP et refus : GTM, Matomo, Facebook, Batch partent quand même.
- Après refus, Matomo se déclare disabled mais les cookies `_pk_*` / `_fbp` restent.
- Sentry Replay est actif sur login **indépendamment** du CMP (chargé dans le HTML login, hors Hagreed).

### Infra

- Java/Struts 2 + Jetty derrière GCP LB, front versionné `14.38.0-rc4`.
- IDs de pages numériques (30002 login, 32073 club, 30058 inscription, 30004 search) = CMS interne.
- `analyticsAjaxAction` est le contrat le plus riche vu ici pour un client (état user, fidélité, tunnel résa/carte).

### Logger

- Le SW Batch casse le health-check CDP. Pour une prochaine capture du tunnel compte, envisager de laisser le SW s’attacher plus longtemps, ou filtrer ce target, avant de clore.
- Interactions suffisantes pour reconstruire clics/focus/saisie. `beforeunload` bruité (iframes about:blank).

## Prochaines captures utiles

Pour documenter le **reste** du produit :

1. Inscription complète (validation e-mail → mot de passe → activation mail)
2. Login réussi + `remember-me` on/off
3. Adhésion « Mon Programme fidélité » et lecture du QR
4. `fidelite.ugc.fr/catalogue-cadeaux.html` + conversion de points
5. Tunnel réservation (sièges, paiement, `reservation_use_fidelity_card`)
6. Forgot password avec captcha résolu
7. Acceptation CMP vs refus (diff cookies / tags)

Rejouer le logger avec `--sensitive safe` si les captures doivent être partagées.
