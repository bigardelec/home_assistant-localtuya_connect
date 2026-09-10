# Notes de version

## 5.2.6-BE.1

### Objectifs de la version

Cette version stabilise le parcours d'installation déjà validé sur du matériel réel et ouvre l'auto-configuration générique à la validation communautaire pour davantage de familles d'appareils Tuya.

### Fonctionnalités validées pendant le développement

- Connexion par QR code avec le Code utilisateur Smart Life / Tuya Smart.
- Récupération de la liste des appareils et des clés locales sans projet Tuya Developer.
- Ajout par adresse IP manuelle lorsque la découverte UDP n'est pas disponible.
- Détection automatique du protocole parmi 3.5, 3.4, 3.3, 3.2 et 3.1, avec mémorisation de la version fonctionnelle.
- Correction du traitement des réponses `CONTROL_NEW` en protocole 3.5 grâce à une file FIFO.
- Amélioration de la stabilité des battements de cœur et des reconnexions.
- Découverte Tuya 3.5 par sollicitation UDP sur le port 7000.
- Auto-configuration des ampoules RGB+CCT.
- Auto-configuration des prises avec puissance, courant, tension et énergie fournie par le micrologiciel lorsqu'elle est disponible.
- Création générique des entités `select` et `number` à partir des métadonnées Tuya.
- Traduction complète en français du parcours de configuration.
- Ajout manuel d'entités après l'auto-configuration.
- Exclusion des appareils déjà configurés dans la liste d'ajout.

### Ajouts destinés à la validation communautaire

- Génération expérimentale d'entités `cover`, `fan`, `climate` et `vacuum` selon la catégorie et les codes sémantiques Tuya.
- Les entités complexes expérimentales sont désactivées par défaut.
- Niveaux de prise en charge explicites : **Validé**, **Implémenté** et **Expérimental**.
- Diagnostics respectueux de la confidentialité contenant les métadonnées sémantiques Tuya nécessaires aux demandes de prise en charge.

### Gestion des appareils hors ligne

- Les appareils volontairement hors tension ne génèrent plus un avertissement à chaque tentative de reconnexion.
- Le passage hors ligne est journalisé une seule fois au niveau `INFO`, puis les tentatives suivantes restent au niveau `DEBUG`.
- Le retour en ligne est signalé une fois au niveau `INFO`.
- Les erreurs réseau courantes pendant la configuration sont traitées comme `cannot_connect` plutôt que comme des exceptions inattendues.
- Les vraies erreurs de protocole, de décodage ou d’authentification restent visibles au niveau `WARNING`.
- Le mécanisme et la fréquence de reconnexion ne sont pas modifiés.

### Limitations connues

- La création générique des `binary_sensor` est implémentée mais pas encore validée sur du matériel réel.
- Les familles complexes restent expérimentales et dépendent des métadonnées exposées par chaque micrologiciel Tuya.
- L'énergie cumulée fournie par `add_ele` peut ne pas être actualisée sur certains appareils.
- Sous Docker Desktop pour Windows, la découverte LAN par diffusion peut ne pas fonctionner correctement ; l'adresse IP peut toujours être renseignée manuellement.

### Dépôts

- LocalTuya Connect : https://github.com/bigardelec/home_assistant-localtuya_connect
- Projet LocalTuya d'origine : https://github.com/rospogrigio/localtuya
