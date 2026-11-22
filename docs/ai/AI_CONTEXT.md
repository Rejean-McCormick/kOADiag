<!-- kOA Doc Server · Docs IA · lot 01 · source datée, non-certifiante -->
# Documentation IA — kOADiag

**Périmètre :** Diagnostic transverse indépendant : inventaire, lacunes documentaires, frontières, services locaux et preuves datées.

**Origine :** snapshot local documenté (20 novembre 2026, ou archive complémentaire). Les chemins et versions actifs sont à vérifier sur le poste avant toute modification.

**Autorité :** kOADiag possède ses observations et rapports locaux. Les tests métier et preuves de déploiement restent sous les autorités des dépôts concernés; GitHub Audit gère ses propres historiques.

## Méthode de travail IA

1. Identifier la campagne, le profil, l’environnement et les dépôts réellement contrôlés.
2. Séparer `PARTIAL` (lacunes de couverture) des erreurs techniques et des échecs de frontières.
3. Utiliser `scan-gaps.json`, `documentary-scope.json` et `effective_config.json` pour des actions de correction ciblées.
4. Rapprocher les preuves des révisions exactes et garder observations nouvelles distinctes des preuves historiques.

## Entrées et validations attestées par les sources

- `Lancer-Diagnostic-kOA-Digital-Ecosystem.cmd  # interface Windows, exécution volontaire uniquement`

*Avant exécution, vérifier les préconditions locales et les effets possibles de la commande. Les commandes sont des points d’entrée documentés, pas des validations effectuées par cet overlay.*

## Frontières à ne jamais franchir

- Jamais de promotion automatique vers GitHub Audit ni de verdict C1/C2/C3 à partir de simples vérifications locales.
- Le parcours transactionnel E2E est séparé et nécessite environnement test isolé et confirmation spécifique.
- Le script officiel IK E2E est détenu par Orgo; ne pas reproduire sa logique et ne pas le lancer implicitement.

## Incertitudes et limites explicites

- La version observée dans le snapshot est documentée 5.7.0; le poste peut avoir une version différente.
- La collecte peut ignorer des fichiers volumineux, sans que ceux-ci soient corrompus.

## Sources à relire

- [`CENTRE-VALIDATION-V570.md`](../../CENTRE-VALIDATION-V570.md) — État documenté des fonctions 5.7.0.
- [`GUIDE-E2E-V570.md`](../../GUIDE-E2E-V570.md) — Garde-fous E2E.
- [`koa_ecosystem_diag/cli.py`](../../koa_ecosystem_diag/cli.py) — CLI et options réelles.
- [`koa_ecosystem_diag/runner.py`](../../koa_ecosystem_diag/runner.py) — Exécution des campagnes.
- [`koa_ecosystem_diag/validation_hub.py`](../../koa_ecosystem_diag/validation_hub.py) — Centre de validation.
- [`koa_ecosystem_diag/documentary_scope.py`](../../koa_ecosystem_diag/documentary_scope.py) — Périmètre documentaire.
- [`koa_ecosystem_diag/full_validation.py`](../../koa_ecosystem_diag/full_validation.py) — Vérification intégrale.
- [`koa-ecosystem-diag.config.json`](../../koa-ecosystem-diag.config.json) — Configuration déclarée.
