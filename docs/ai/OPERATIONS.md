<!-- kOA Doc Server · Docs IA · lot 04 · proposition non certifiante -->
# Procédure IA — kOADiag

**Objet :** Observation native, pas promotion des preuves.

**Source de rédaction :** `kOADiag_Code_snapshot.zip` (capture datée). Ce document ne déclare pas que les commandes ont été exécutées sur le poste local.

## Parcours recommandé

1. Vérifier `koa-ecosystem-diag.config.json` et la version du moteur avant toute campagne.
2. Séparer l’inventaire des dépôts, le balayage documentaire et la validation des frontières : une source trop volumineuse produit une lacune, pas nécessairement une erreur.
3. Éviter les scans d’archives/staging et les suppressions de données pour forcer un statut PASS.
4. Consigner l’identifiant de campagne et les chemins de rapports locaux sans remplacer les résultats précédemment admis.
5. Dans Doc Server, afficher les résultats comme observations locales non promues; les preuves de bout en bout restent à établir.

## Documents propriétaires à consulter

`koa_ecosystem_diag/cli.py`, `koa_ecosystem_diag/runner.py`, `koa_ecosystem_diag/full_validation.py`, `GUIDE-E2E-V570.md`.

## Vérifications avant effet

- Confirmer la racine, la révision et les versions du dépôt réellement installé.
- Ne pas substituer la présente fiche aux `AGENTS.md`, contrats, ADR et validations propriétaires.
- Ne pas copier de secrets, données privées, rapports de maturité ou sauvegardes dans un ZIP public.
- Exécuter tout diagnostic, synchronisation ou publication **seulement après décision explicite**; préserver les rapports existants.
- Le Framework v11 demeure **facultatif et non bloquant** pour Doc Server.
