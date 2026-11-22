<!-- kOA Doc Server · Docs IA · lot 01 · source datée, non-certifiante -->
# Documentation IA — kOADiag

**Périmètre :** Diagnostic transverse indépendant : inventaire, lacunes documentaires, frontières, services locaux et preuves datées.

**Origine :** snapshot local documenté (20 novembre 2026, ou archive complémentaire). Les chemins et versions actifs sont à vérifier sur le poste avant toute modification.

**Autorité :** kOADiag possède ses observations et rapports locaux. Les tests métier et preuves de déploiement restent sous les autorités des dépôts concernés; GitHub Audit gère ses propres historiques.

## Ordre de lecture conseillé à un agent

1. [`CENTRE-VALIDATION-V570.md`](../../CENTRE-VALIDATION-V570.md) — État documenté des fonctions 5.7.0.
2. [`GUIDE-E2E-V570.md`](../../GUIDE-E2E-V570.md) — Garde-fous E2E.
3. [`koa_ecosystem_diag/cli.py`](../../koa_ecosystem_diag/cli.py) — CLI et options réelles.
4. [`koa_ecosystem_diag/runner.py`](../../koa_ecosystem_diag/runner.py) — Exécution des campagnes.
5. [`koa_ecosystem_diag/validation_hub.py`](../../koa_ecosystem_diag/validation_hub.py) — Centre de validation.
6. [`koa_ecosystem_diag/documentary_scope.py`](../../koa_ecosystem_diag/documentary_scope.py) — Périmètre documentaire.
7. [`koa_ecosystem_diag/full_validation.py`](../../koa_ecosystem_diag/full_validation.py) — Vérification intégrale.
8. [`koa-ecosystem-diag.config.json`](../../koa-ecosystem-diag.config.json) — Configuration déclarée.

## Documents produits par cet overlay

- [`AI_CONTEXT.md`](AI_CONTEXT.md) — limites, parcours et points de contrôle.
- `PROFIL_INGENIERIE.md` — produit **sur demande** à partir d'un scan RepoSurveyor du code local; ce fichier n'est pas fourni par le lot rédactionnel.
- `AGENTS.md` à la racine — consignes de dépôt existantes conservées ou nouvelles si elles n'existaient pas.

## Règles transversales

- Une capture documentaire n'établit ni conformité, ni maturité, ni disponibilité en production.
- Ne pas remplacer contrats, ADR, README ou preuves propriétaires par cette aide de navigation.
- Nouveau Framework v11 : lire le profil effectivement adopté; ne jamais imposer une migration par défaut.

## Procédure opérationnelle proposée (lot 04)

- [`OPERATIONS.md`](OPERATIONS.md) — parcours concret et points de contrôle à vérifier avant tout effet.
