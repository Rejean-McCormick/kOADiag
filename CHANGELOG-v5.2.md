# v5.2 — Diagnostic du kOA Digital Ecosystem

## Ajouts
- Registre persistant `koa-ecosystem-diag.boundaries.local.json` : décisions humaines, jamais auto-approuvées.
- Onglet graphique **Registre des frontières** : recherche, qualification, statut obligatoire/optionnel, protocole, route et identité Audit.
- Synchronisation des observations à chaque scan, maintien des décisions des relations anciennes ou non retrouvées.
- Instantané du registre par campagne et export CSV détaillé.
- Priorisation des fichiers de frontière dans la collecte, budget à 8 500 fichiers/dépôt, télémétrie des exclusions/limites.
- Rapprochement explicite des inventaires : 53 dépôts dans le registre Diag, 49 dans la référence Audit du 10 novembre 2026, quatre différences à examiner.
- Métriques de revue dans les rapports de couverture, sans modifier le contrat public-safe de l'export Audit.

## Maintenu
- 13 niveaux et processus isolés LevelUpDiag.
- UI Tkinter, logo, thème `#1E6864`, campagnes et historique.
- Appariement API/événements et parcours E2E des v5.x.
- Export vers GitHub Audit v0.22.0 (sans traces sensibles).

## Non inclus
- Certification E2E globale, endpoints runtime automatiquement approuvés, tests internes d'applications ou modification des 53 dépôts.
- Fichier local de décisions ou historiques ; aucun `.patch`.

## Validation de livraison
- 22 tests automatisés ; lancement UI sous Tkinter ; campagne simulée à 53 chemins de dépôts ; import du bundle dans l'adaptateur Audit v0.22.0.
- Aucun scan n'a été effectué sur les vrais dépôts `C:\mycode`.
