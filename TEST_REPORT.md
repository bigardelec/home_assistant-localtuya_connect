# Rapport de validation — 5.2.6-BE.1

## Validation réalisée sur du matériel réel

Le parcours de cette version a été testé sur deux familles d'appareils :

- prises Tuya de catégorie `cz`, avec relais et mesures électriques ;
- ampoules Tuya RGB+CCT de catégorie `dj`.

Le jeu de métadonnées anonymisé utilisé pour les tests de régression contient **18 appareils : 9 `cz` et 9 `dj`**. L'auto-configuration a généré les entités attendues de type interrupteur, lumière et capteur sans rejet lié à une incompatibilité de type.

## Parcours utilisateur validés

Les éléments suivants ont été testés pendant le développement :

- connexion par QR code ;
- récupération des clés locales ;
- ajout avec adresse IP manuelle ;
- détection automatique du protocole ;
- détection des DPS ;
- génération automatique des entités ;
- lecture des valeurs et envoi de commandes ;
- nommage et traductions des entités ;
- exclusion des appareils déjà configurés ;
- ajout manuel de DPS après une auto-configuration.

## Validation de la journalisation des appareils hors tension

Le comportement des appareils temporairement indisponibles a également été vérifié avec des ampoules coupées physiquement à l’interrupteur. Le correctif anti-spam conserve les tentatives de reconnexion automatiques tout en évitant les avertissements répétés dans les journaux Home Assistant.

- le premier passage hors ligne est signalé une seule fois au niveau `INFO` ;
- les tentatives suivantes restent au niveau `DEBUG` ;
- les erreurs réseau courantes pendant la configuration sont classées `cannot_connect` ;
- les erreurs réelles de protocole ou d’authentification restent visibles au niveau `WARNING`.

## Vérifications synthétiques de l'auto-configuration

Des jeux de métadonnées synthétiques ont également été utilisés pour vérifier la construction des familles expérimentales :

- `cl` → entité `cover` désactivée par défaut avec ouverture, arrêt, fermeture et position en pourcentage ;
- `fs` → entité `fan` désactivée par défaut avec vitesse, oscillation et direction ;
- `kt` → entité `climate` désactivée par défaut avec température cible, température actuelle et mode HVAC reconnu ;
- `sd` → entité `vacuum` désactivée par défaut avec état/mode, démarrage/pause, batterie, aspiration et localisation lorsque les métadonnées correspondantes existent.

Ces vérifications synthétiques valident uniquement la construction de la configuration. Elles ne remplacent pas une validation sur du matériel réel.

Pour cette raison, les familles `cover`, `fan`, `climate` et `vacuum` restent marquées **Expérimental**.
