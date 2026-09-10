# Matrice de prise en charge de l'auto-configuration

Le niveau indiqué concerne l'**auto-configuration**. Un appareil non reconnu automatiquement peut toujours être configuré manuellement lorsque la plateforme LocalTuya correspondante le permet.

| Famille | Plateforme Home Assistant | Niveau | État par défaut | Règle de reconnaissance |
|---|---|---|---|---|
| Relais de prise / prise connectée | `switch` | Validé | Activé | Booléen `switch_1` |
| Mesures électriques | `sensor` | Validé | Activé, sauf énergie | `cur_power`, `cur_current`, `cur_voltage`, `add_ele` |
| Ampoule RGB/CCT | `light` | Validé | Activé | `switch_led` avec les codes sémantiques de luminosité, température et couleur |
| Énumération modifiable | `select` | Validé | Désactivé | `Enum` modifiable avec une plage de valeurs déclarée |
| Entier modifiable | `number` | Validé | Désactivé | `Integer` modifiable avec min/max/pas et `scale=0` |
| Booléen en lecture seule | `binary_sensor` | Implémenté | Désactivé | `Boolean` en lecture seule |
| Volet / rideau | `cover` | Expérimental | Désactivé | catégorie `cl`/`clkg`, `control=open/stop/close`, position 0–100 facultative |
| Ventilateur | `fan` | Expérimental | Désactivé | catégorie `fs`/`fsd`/certains `kj`, avec interrupteur, vitesse, oscillation ou direction sémantiques |
| Chauffage / climatisation | `climate` | Expérimental | Désactivé | catégorie `wk`/`kt`/`ktkzq`/`qn` compatible, avec interrupteur, température cible/actuelle et mode reconnu |
| Aspirateur robot | `vacuum` | Expérimental | Désactivé | catégorie `sd`, état/mode et `power_go` ou interrupteur de nettoyage compatible |

## Pourquoi les familles complexes sont-elles désactivées par défaut ?

Les codes standards Tuya sont beaucoup plus fiables qu'une reconnaissance basée sur une marque ou un modèle. Cependant, les variantes de micrologiciel peuvent modifier certaines valeurs d'énumération ou certains comportements.

Une entité expérimentale désactivée par défaut permet donc à l'utilisateur de l'inspecter et de l'activer volontairement, sans exposer automatiquement une commande qui n'a pas encore été validée sur son matériel.

## Configuration de secours

Les capacités inconnues ou rejetées par l'auto-configuration ne sont pas perdues. Le parcours classique de configuration manuelle de LocalTuya reste disponible.

Un appareil peut donc être partiellement auto-configuré puis complété manuellement avec les DPS nécessaires.
