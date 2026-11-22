# Diagnostic du kOA Digital Ecosystem — changelog v5.0

- **Scheduler :** `PARTIAL` ne provoque plus dix `BLOCKED` en cascade ; les niveaux continuent sur la preuve disponible, avec propagation explicite de la limitation.
- **Collecte :** limite par dépôt 900 → 3500 par défaut, configurable, bornée et visible.
- **Contrats :** URN `$ref` traitées comme références externes ; empreintes divergentes sous même `$id` passées en revue plutôt que déclarées incompatibles sans contrainte de version.
- **API :** index des routes entrantes et exigences d'interface `expected_api_links`, avec CSV dédié.
- **E2E :** N12 + campagne `e2e` + rapprochement conservateur émission/réception/réponse sur chaque saut d'un parcours déclaré.
- **Preuves :** indépendance des fichiers d'export des deux côtés, support `journey_id`, `response_ok`, statut de corrélation.
- **Rapports :** `coverage`, `delta.json`, `priorites.txt`, matrice inter-repos CSV, export des parcours E2E.
- **UI :** synthèse, onglet Parcours E2E, configuration locale accessible, 13 niveaux, branding #1E6864 + logo.
- **Compatibilité :** manifeste/report/synthèse LevelUpDiag v2 conservés ; anciens rapports préservés ; configuration locale non écrasée.
- **Limite conservée :** aucune certification de l'écosystème A à Z sans couverture exhaustive documentée et preuves indépendantes de toutes les frontières.
