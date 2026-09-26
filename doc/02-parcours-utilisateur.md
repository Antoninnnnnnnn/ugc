# 02 — Parcours utilisateur

Chronologie locale (Europe/Paris). Toutes les heures viennent des événements d’interaction et de navigation.

## Timeline

| Heure | Acteur | Action |
|---|---|---|
| 22:23:00.802 | logger | Démarrage, Chrome attaché |
| 22:23:10.068 | page | Navigation depuis `about:blank` |
| 22:23:10.071 | réseau | GET Dealabs `/visit/threadmain/3417894` |
| 22:23:10.694 | réseau | 302 → `path.dealabs.com/pepper-fr/redirect` |
| 22:23:10.832 | réseau | 302 → `dealabs.digidip.net/visit` |
| 22:23:11.004 | réseau | 302 → **`https://www.ugc.fr/club-fidelite.html`** (200, 67 ms) |
| 22:23:11.088 | nav | `frameNavigated` club-fidelite |
| 22:23:11.170–11.856 | page | CMP Hagreed, GTM, Matomo, Batch, Facebook Pixel, pubs Ajax |
| 22:23:13.739 | user | Focus bouton **« Continuer sans accepter → »** |
| 22:23:13.820 | user | Clic refus cookies (`data-type="decline_all"`) |
| 22:23:13.843 | réseau | Hagreed `POST /api/hit` type `CN_DECLINE` |
| 22:23:14.709 | user | Clic zone titre (près du CTA) |
| 22:23:14.907 | user | Focus lien `login.html` |
| 22:23:14.969 | user | Clic **« Rejoindre le programme fidélité »** |
| 22:23:14.989 | réseau | GET **`/login.html`** (200) |
| 22:23:15.179 | nav | Frame principale = login |
| 22:23:15.266 | cookies | **`JSESSIONID`** posé (session, HttpOnly) |
| 22:23:15.344 | iframes | Friendly Captcha agent + 2 widgets |
| 22:23:16.431 | user | Focus onglet **« Je crée un compte »** |
| 22:23:16.474 | user | Clic `#nav-login-2-tab` |
| 22:23:17.898 | user | Focus `#email-2` (`inscriptionBean.email`) |
| 22:23:17.991 | user | Clic dans le champ e-mail |
| 22:23:19.341 | user | Input valeur `bien` |
| 22:23:19.924 | user | Input valeur `bien@` |
| 22:23:20.479 | captcha | Workers blob Friendly Captcha |
| 22:23:22.029 | logger | Timeout CDP `Network.enable` (SW Batch) |
| 22:23:27.546 | logger | Arrêt en erreur |

## Chaîne d’affiliation Dealabs

Thread Dealabs **3417894**, produit Pepper **`ppr-fr-1928513538`**.

```
GET https://www.dealabs.com/visit/threadmain/3417894
  302 Location: https://path.dealabs.com/pepper-fr/redirect
                 ?url=https://www.ugc.fr/club-fidelite.html
                 &product=ppr-fr-1928513538
                 &referer=https://www.dealabs.com

GET path.dealabs.com  (Cloudflare + PHP 8.5.3, API Gateway)
  302 Location: https://dealabs.digidip.net/visit
                 ?url=https://www.ugc.fr/club-fidelite.html
                 &ppref=https://www.dealabs.com
                 &ref=ppr-fr-1928513538

GET dealabs.digidip.net  (nginx, Clickdip)
  Headers Digidip:
    x-digidip-location: https://www.ugc.fr/club-fidelite.html
    x-digidip-program: 0
    x-digidip-subid: 1c003m2v2ft5s
    x-digidip-tracking-app: clickdip
    x-digidip-tracking-server: 45
  302 Location: https://www.ugc.fr/club-fidelite.html
```

Les cookies Dealabs (`pepper_session`, `f_v`, `xsrf_t`, `lcl=3417894`) **ne traversent pas** vers `path.dealabs.com` (`DomainMismatch`). L’affiliation Digidip ne dépose **aucun cookie** sur `ugc.fr`. UGC reçoit une navigation document classique, sans query string d’affiliation.

## Page Club fidélité

Titre : **« Le Programme fidélité UGC : plus simple, plus généreux »**.

Fil d’Ariane tracking Facebook : `ACCUEIL / CARTES & OFFRES / LE PROGRAMME FIDÉLITÉ UGC`.

CTA principal :

```html
<a href="login.html" class="cta cta--pink pad-card-button" role="button">
  <span>Rejoindre le programme fidélité</span>
</a>
```

Le clic Facebook Pixel associé est `SubscribedButtonClick` avec destination `https://www.ugc.fr/login.html`.

## Page connexion

Titre : **« UGC - Connexion »**. Deux onglets Bootstrap :

1. `#nav-login-1` — **Je m’identifie** (actif par défaut)
2. `#nav-login-2` — **Je crée un compte** (cliqué)

L’utilisateur n’utilise pas le formulaire de login. Il bascule sur l’inscription et commence à saisir un e-mail. **Aucun POST Struts / Spring Security n’est envoyé.**

## Ce qui n’a pas eu lieu

- Soumission login (`j_spring_security_check`)
- Soumission inscription (`monCompteInscriptionAction!validationEmail`)
- Mot de passe oublié / renvoi d’e-mail d’activation
- Acceptation du CMP (refus total)
- Navigation vers `fidelite.ugc.fr` (catalogue cadeaux, lien sortant non cliqué)
- Réservation, achat, QR code fidélité
