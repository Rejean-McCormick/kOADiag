# Diagnostic du kOA Digital Ecosystem — v5.1

- **Pont vers GitHub Audit v0.22.0** : export automatique et manuel d'une archive LevelUpDiag `latest/summary.json` + `latest/levels/Nxx/result.json` compatible avec son importateur.
- **Minimisation des données** : export à liste blanche, sans `target_repo_root`, findings, chemins, URLs, traces, payloads et configuration.
- **Deux moteurs distincts** : l'audit reste le consommateur passif ; aucun diagnostic interne exécuté par le pont.
- **Sécurité** : vérification des identités de campagne et verdicts des 13 niveaux, refus de sortie vers `docs/`, refus de remplacer une archive différente sous le même nom de campagne, export déterministe.
- **UI** : bouton `EXPORT AUDIT` pour la campagne sélectionnée (ou la dernière), palette `#1E6864` et logo existants conservés ; correction du sous-titre à **13 niveaux**.
- **CLI** : `export-audit` avec `--run-root` et `--out`.
- **Registre de revue** : `frontieres-a-qualifier.csv`, clés stables, valeurs CSV sécurisées, aucune validation automatique.
- **Compatibilité** : structure LevelUpDiag v2 inchangée ; manifest et résultats annotés v5.1 ; configurations locales et historiques inchangés.

**Non inclus** : changement automatique des 53 dépôts, nouvelle certification E2E, fusion des outils, synchronisation publique vers GitHub Pages.
