# 06 — Authentification, inscription, captcha

La page `login.html` est le **point d’entrée compte**. L’auth n’est pas un JSON JWT : c’est un formulaire HTML Spring Security, session cookie, CSRF.

Aucun de ces POST n’a été exécuté dans la session. Le contrat ci-dessous vient du **HTML + JS inline** capturés.

## Session

Au premier GET `login.html`, le serveur pose :

| Cookie | Portée | Flags | Durée |
|---|---|---|---|
| `JSESSIONID` | `www.ugc.fr` `/` | HttpOnly, Secure, SameSite=Lax, session | expire à la fermeture du navigateur |

Valeur observée : UUID encodé base64 (forme `NGNmN2RmOTUt…`). Cookie de session servlet Java standard.

`club-fidelite.html` (page cachée 30 min) **ne pose pas** de `JSESSIONID`.

## Login — Spring Security

```
POST https://www.ugc.fr/j_spring_security_check
Content-Type: application/x-www-form-urlencoded
```

| Champ | Type | Obligatoire | Rôle |
|---|---|---|---|
| `_csrf` | hidden | oui | Token anti-CSRF Spring (UUID) |
| `j_username` | email `#mail` | oui | E-mail |
| `j_password` | password `#password` | oui | Mot de passe (`autocomplete=off`) |
| `remember-me` | checkbox | non | « Se souvenir de moi » |
| token Friendly Captcha | injecté par le widget | oui si widget présent | Proof-of-work |

Submit : `disableAndSubmit(this, true)` puis `submitWithBootstrapClientValidation` → `j_spring_security_check_form_startCaptchaAndSubmit()`.

Le captcha est en `data-start="none"` : il ne démarre **qu’au clic** « Je me connecte ». S’il n’est pas `completed`, `widget.start()` et le submit est bloqué (`return false`). Sur `frc:widget.complete`, le JS re-clique `#connectLink`.

Le token CSRF est **dans le HTML** de `login.html`. Il change à chaque GET (page no-store). Ne pas le réutiliser hors de la session qui l’a reçu.

## Inscription — étape e-mail

Onglet `#nav-login-2`. Deux formulaires :

### 1. Formulaire visible (Ajax)

```
POST /monCompteInscriptionAction!validationEmail.action
```

| Champ | Valeur |
|---|---|
| `page` | `30058` |
| `inscriptionBean.email` | e-mail (`#email-2`) |

Bouton Struts2-jQuery : `targets = "errorField"`, spinner Alteis, **pas de CSRF visible**, **pas de captcha** sur ce formulaire.

C’est une validation d’e-mail (disponibilité / format / jetable). La suite (mot de passe, profil) est hors capture : probablement un autre GET/POST `monCompteInscriptionAction` après succès.

### 2. Formulaire hidden de redirection

```
POST /monCompteInscriptionAction.action
page=30058
inscriptionBean.email=  (copié dans #hidden_email)
```

Non déclenché.

Dans la session, l’utilisateur a tapé `bien` puis `bien@` dans `#email-2` sans soumettre.

## Mot de passe oublié

Modal `#modal-forgotten-password` :

```
POST /forgotAction.action
email=
errorStyle=color--pink
```

Friendly Captcha **identique** au login (`forgotForm_startCaptchaAndSubmit`). Pas de `_csrf` dans le HTML capturé.

## Renvoi du mail d’activation

Modal `#modal-resend-email` :

```
POST /resendActivationEmailAction.action
email=
errorStyle=color--pink
```

Pas de captcha ni CSRF dans le HTML capturé.

## Friendly Captcha

| Paramètre | Valeur |
|---|---|
| SDK | `@friendlycaptcha/sdk@0.1.31` (jsDelivr, module + nomodule) |
| Sitekey publique | `FCMR306TFOLA6D49` |
| API | `https://global.frcapi.com/api/v2/` |
| Mode widget | `data-start="none"` |
| Session FRC | `sess_id` dans `sessionStorage.frc_sid` |
| Compteur widgets | `sessionStorage.frc_sc` (incrémenté 1→2→3) |

Endpoints vus :

```
GET  /api/v2/captcha/agent?origin=https://www.ugc.fr&sess_id=…&agent_id=…
GET  /api/v2/captcha/widget?origin=…&lang=fr&sitekey=FCMR306TFOLA6D49
GET  /api/v2/captcha/ping     (annulé / ERR_ABORTED)
```

Sur login, **un agent + deux widgets** (login form + forgot form). Workers `blob:https://global.frcapi.com/…` pour le proof-of-work. Le captcha n’a pas été résolu : pas de submit.

## Sentry (page login seulement)

- Loader : `https://js.sentry-cdn.com/{public_key}.min.js`
- Bundle : `browser.sentry-cdn.com/7.120.4/bundle.tracing.replay.min.js`
- Intégrations : BrowserTracing + **Replay**
- Replay sessionStorage : `sentryReplaySession`
- Ingest : `o4505228090933248.ingest.us.sentry.io` projet `4505233466064896`
- Les deux envelopes de la session sont **429** (quota). Le replay (170 Ko) n’est pas accepté.

Sentry n’est **pas** chargé sur `club-fidelite.html`.

## Implications pour un client automatisé

1. Charger `login.html` pour obtenir `JSESSIONID` + `_csrf`.
2. Résoudre Friendly Captcha (sitekey publique, challenge FRC) **avant** le POST login / forgot.
3. Poster `j_username` / `j_password` / `_csrf` / token FRC en `application/x-www-form-urlencoded`, same-origin, cookie session.
4. L’inscription e-mail est un POST Struts Ajax distinct, sans captcha dans le HTML actuel.
5. Après login, le dataLayer expose `has_just_logged_in`, `has_user_info`, `is_fid_user`, `fid_points`, `userId`.
6. Le programme fidélité lui-même n’est **pas** sur `login.html` : l’adhésion réelle est « Mon Programme fidélité » dans le compte (hors capture).
