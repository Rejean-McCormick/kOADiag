# kOADiag 5.6.1 — Causes et preuves LevelUpDiag

- Les sous-vues **Causes et preuves** et **Niveaux LevelUpDiag** sont ajoutées au Centre de validation ; les onglets antérieurs sont conservés.
- Les analyses s’appuient seulement sur `summary.json`, `effective_config.json` et `levels/Nxx/result.json` de la campagne LevelUpDiag réellement exécutée.
- Les rapports du Centre incluent désormais `causes.csv` et `niveaux.csv`.
- La synthèse distingue collecte incomplète, traces manquantes, frontières non prouvées, parcours incomplets, qualification en attente et E2E non exécuté.
- Les sources d’export de preuves ne sont ni inventées ni chargées automatiquement ; les fichiers `.env`, tokens, bases et données métier sont inchangés.
- Les 16 composants facultatifs non démarrés ne deviennent pas des « pannes » par déduction.
- La validation approfondie reste passive et n’exécute pas N14 ; utiliser le kit officiel séparément sur une pile isolée après contrôle des données de test.

## Après installation

1. Ouvrir kOADiag et **Centre de validation → Validation approfondie**.
2. Ouvrir **Causes et preuves** pour les actions et **Niveaux LevelUpDiag** pour les constats exacts.
3. Double-cliquer une cause ou un niveau pour les détails.
4. Le bouton **RAPPORT** ouvre le dossier avec `validation.json`, `synthese.txt`, `causes.csv`, `niveaux.csv` et les exports existants.

Le patch n’ajuste **aucun verdict** artificiellement. Un historique ancien du Centre v5.6.0 ne contient pas les nouveaux champs : relancer une validation approfondie pour alimenter ces vues.
