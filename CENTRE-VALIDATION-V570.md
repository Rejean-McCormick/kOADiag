# kOADiag v5.7.0 — mise à jour consolidée

Cette version complète **sans suppression** le Centre de validation 5.6.1, ses 12 onglets principaux, le superviseur C0, l'historique, les niveaux N00–N14, la matrice de preuves et les fonctions de qualification existantes.

| Fonction | Avant | v5.7.0 |
|---|---|---|
| Validation rapide | 21 ports + liens C0 | Conservée, non destructive |
| Validation approfondie | Santé + LevelUpDiag | Conservée + catalogue des suites propriétaires, bilan par domaine et plan de correction |
| Causes et preuves | 7 causes, N00–N14 | Conservées, sans verdicts artificiellement modifiés |
| Plan de correction | Exports à consulter manuellement | Sous-page interactive alimentée par `scan-gaps.json`, `documentary-scope.json`, `inventory-alignment.json`, `effective_config.json` |
| Interaction Kernel | Explication et lien | Sous-page de précontrôle réel + test officiel opt-in avec double confirmation |
| E2E | Non exécuté | Réservé à un World et deux bases de test déclarées isolées ; aucun déclenchement automatique |
| Rapports | JSON, CSV, TXT | + `remediations.csv`, `tests_applicatifs.csv`, résultats IK E2E assainis |
| Compatibilité | 5.6.1 installé | Mise à jour ciblée, sauvegarde et restauration ; pas d'écrasement de fichiers divergents |

## Problèmes de la campagne du 20 novembre abordés

- **10 fichiers surdimensionnés** : regroupement exact par dépôt/dossier, sans augmentation aveugle du plafond de lecture.
- **Un document dont l'empreinte a changé** : signalé pour validation humaine, jamais réapprouvé automatiquement.
- **Inventaires 53/49 divergents** : liste des différences, conservation de l'historique.
- **Sources de traces IK absentes** : action guidée pour récupérer des exports assainis et signés, pas de fausse preuve générée.
- **N14 non exécuté** : test E2E désormais accessible séparément dans le Centre ; pas dans le mode « approfondi » non destructif.
- **16 services optionnels arrêtés** : rapportés comme non disponibles, pas comme collisions de ports ; bilan essentiel séparé.

## Limites réelles

Les tests propriétaires des 55 dépôts n'ont pas tous été écrits pour une exécution automatisée inter-apps. kOADiag en liste les entrées reconnues mais ne les exécute pas sans contrat de sécurité. La collecte de traces certifiées Orgo/Konnaxion exige des observations de leurs systèmes en fonctionnement, et non seulement la présence d'un fichier de code. La migration des scripts historiques `prepare-local.ps1` et des déploiements hors PC reste la responsabilité des dépôts propriétaires.
