# Sécurité et diagnostics

Les informations d'authentification utilisées par LocalTuya Connect doivent être considérées comme confidentielles.

## Informations à ne jamais publier

- `local_key` ;
- jetons d'accès ou de rafraîchissement Smart Life / Tuya ;
- données de jeton utilisées pour la connexion par QR code ;
- identifiants de compte ;
- identifiants uniques d'appareils, sauf nécessité particulière et en connaissance de leur impact sur la confidentialité ;
- adresses IP ou informations réseau privées non nécessaires au diagnostic.

## Protection des diagnostics

LocalTuya Connect assainit récursivement les diagnostics Home Assistant afin de masquer les clés locales, jetons Cloud/QR, identifiants stables de compte ou d'appareil et adresses réseau.

Les métadonnées sémantiques Tuya utiles au support sont volontairement conservées, notamment :

- la catégorie Tuya ;
- les codes d'état sémantiques ;
- les correspondances avec les DPS numériques ;
- les types de données ;
- les unités ;
- les plages et valeurs autorisées.

Ces informations sont nécessaires pour améliorer la prise en charge générique des appareils sans dépendre d'une marque ou d'un modèle particulier.

**Vérifiez toujours un fichier de diagnostics avant de le publier sur GitHub ou ailleurs.**
