# Documentation UGC.fr — session du 26 septembre 2026

Analyse complète de la capture Chrome Network Logger
`session_20260926_222300_798_20272_f3ab`.

La session dure **~27 secondes**. Elle reconstitue un parcours Dealabs → page Club fidélité UGC → page de connexion / création de compte. L’inscription n’est **pas soumise** : l’utilisateur ouvre l’onglet « Je crée un compte » et commence à taper un e-mail. La capture se termine en **erreur CDP** (`Network.enable` timeout sur le service worker Batch).

## Synthèse

| Élément | Valeur |
|---|---|
| Site | `https://www.ugc.fr` |
| Stack | Jetty 10.0.25 + Apache Struts 2 + Spring Security + jQuery 3.4.1 |
| Front | `14.38.0-rc4` — build `4ff228808df8806d71d0b24a874e27fb` |
| Locale | `fr_FR` |
| CDN / LB | Google (`via: 1.1 google`, IP `35.244.207.4`) |
| Auth | `POST /j_spring_security_check` + CSRF + Friendly Captcha |
| Inscription | `POST /monCompteInscriptionAction!validationEmail.action` |
| CMP cookies | Hagreed (refus « Continuer sans accepter ») |
| Session HTTP | Cookie `JSESSIONID` (HttpOnly, Secure, SameSite=Lax) posé sur `login.html` |

## Parcours observé

```
Dealabs thread 3417894
  → path.dealabs.com (Pepper)
    → dealabs.digidip.net (affiliation)
      → www.ugc.fr/club-fidelite.html
        → refus cookies Hagreed
          → clic « Rejoindre le programme fidélité »
            → www.ugc.fr/login.html
              → onglet « Je crée un compte »
                → saisie partielle e-mail
                  → capture interrompue (erreur logger)
```

## Sommaire

1. [Métadonnées de capture](01-session-capture.md)
2. [Parcours utilisateur](02-parcours-utilisateur.md)
3. [Architecture technique](03-architecture.md)
4. [Pages, sitemap et IDs CMS](04-pages-et-sitemap.md)
5. [API first-party](05-api-first-party.md)
6. [Authentification, inscription, captcha](06-authentification.md)
7. [Cookies et Web Storage](07-cookies-et-storage.md)
8. [Services tiers](08-services-tiers.md)
9. [Consentement Hagreed](09-consentement-hagreed.md)
10. [Limites de la capture et observations](10-limites-et-observations.md)

## Source brute

Les fichiers canoniques restent dans :

`chrome-network-logger/session_20260926_222300_798_20272_f3ab/`

Cette documentation **ne recopie pas** les secrets de session (`JSESSIONID`, `_csrf`, tokens Dealabs). Ils existent dans la capture brute (`sensitiveMode: raw`).

## Automation HTTP (`ugc_flow`)

Client **sans navigateur** (httpx), un compte par exécution, ~50 s :

1. `GET /login.html`, puis `validationEmail` (Ajax) et `redirect_form`
2. `POST monCompteInscriptionAction!inscription` (e-mail, mot de passe, CGU, case « plus de 15 ans », jeton Friendly Captcha **v2**)
3. Lien `activationMonCompte` récupéré par IMAP Gmail (domaines catch-all), puis `GET` (« Votre compte UGC est bien activé »)
4. `POST /j_spring_security_check` (CSRF + captcha v2) ; le cookie `.ugc.fr` `authToken_prod` sert de SSO vers `fidelite.ugc.fr`
5. `POST https://fidelite.ugc.fr/adhesion.html` (`membershipForm`, `method:join`) : prénom, nom, date `dd/mm/yy`, code postal, pays, newsletter et CGU obligatoires. Succès = « Mes points fidélité : 100 POINTS »

```bash
python -m pip install -r requirements.txt
copy .env.example .env
py main.py                 # menu interactif
py main.py create 10 -t 3  # 10 comptes, 3 en parallèle (max 5)
py main.py list [-a]       # comptes (-a : inclure les échecs)
py main.py export          # comptes OK -> accounts.csv (email;password;points;statut;run_id)
py main.py check           # proxies, solde captcha, IMAP
```

Captcha : **CapMonster Cloud** (`CustomTask` / `class: friendly` / `apiGetLib` = `site.min.js`). CapSolver ne produit que des jetons v1, que UGC rejette avec « Une demande a déjà été envoyée… ».

Secrets dans `.env` (gitignoré). Proxies Evomi : `proxy.txt` (gitignoré), une ligne `http://host:port:user:pass`. Dumps et `credentials.json` : `runs/<run>/`.

Le menu propose aussi « Boîte mail » (derniers mails reçus) et « Terminer l'adhésion d'un compte activé » (connexion puis adhésion pour un compte resté sans fidélité).
