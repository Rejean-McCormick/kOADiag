# Diagnostic du kOA Digital Ecosystem — v5.2 (override direct)

**Périmètre :** fiabilisation de la collecte et registre de qualification des frontières inter-repos. Les diagnostics internes des applications restent exclus.

## Installation — aucun patch Git

1. Fermer l'application Diag et sauvegarder les fichiers locaux modifiés.
2. Identifier **la racine du dépôt Diagnostic**, celle contenant `Diagnostic-kOA-Digital-Ecosystem.pyw`, `koa-ecosystem-diag.config.json` et `koa_ecosystem_diag/` (par exemple `C:\mycode\kOA_Digital_Ecosystem\kOADiag` si c'est ton installation).
3. Extraire le **contenu** de ce ZIP à cette racine, fusionner les dossiers, accepter le remplacement des fichiers communs.
4. Ne **pas** extraire à la racine `C:\mycode` à moins que le script principal s'y trouve réellement.
5. Démarrer : `py -3 "C:\mycode\kOA_Digital_Ecosystem\kOADiag\Diagnostic-kOA-Digital-Ecosystem.pyw"` (adapter le chemin si nécessaire).
6. Lancer `complet`, puis ouvrir **Registre des frontières** pour qualifier les relations.

Aucun `.patch`, aucune commande `git apply`, `git commit` ou `git push` n'est nécessaire. L'archive ne contient ni fichiers `*.local.json`, ni campagnes privées ni rapports.

## Nouveau registre persistant

Le fichier `koa-ecosystem-diag.boundaries.local.json` est **créé à la racine du Diagnostic lors du premier scan** ; il est **absent du ZIP** afin de ne jamais écraser les décisions humaines. Chaque nouvelle relation est `UNREVIEWED` et `required = null`. Dans l'onglet **Registre des frontières**, ouvrir une ligne pour la qualifier :

- `APPROVED` : valider son appartenance au périmètre ; choisir explicitement **Obligatoire** ou **Optionnelle**.
- `REJECTED` : exclure du périmètre vérifié après revue ; le diagnostic ne supprime pas l'observation.
- `DEFERRED` : reporter une décision ; couverture toujours incomplète.
- `UNREVIEWED` : nouvelle ou non encore qualifiée ; aucune approbation automatique.

La décision n'est **pas** une preuve d'échange. Les données du dernier scan (`last_qualification`, `observed`) sont actualisées, mais aucune décision humaine n'est effacée. Les relations historiques non retrouvées restent visibles. Les identifiants sont compatibles avec les clés CSV de la v5.1.

Pendant l'exécution d'une campagne l'éditeur verrouille les modifications. Les campagnes conservent un instantané privé `registry-snapshot.json` et exportent `exports/registre-frontieres.csv` en lecture seule.

## Collecte et couverture

La limite par défaut passe de 3 500 à **8 500 fichiers source/configuration par dépôt**. Le scanner privilégie les noms de fichiers de frontière (API, routes, clients, contrats, schémas, événements, interop, SDK…), puis le code général, puis la configuration. Les fichiers volumineux ou illisibles et les dépôts sans code/configuration dans le périmètre sont comptabilisés séparément. **Un scan priorisé ne constitue pas une couverture exhaustive du contenu du dépôt.** Les dossiers exclus (ex. docs, tests) restent exclus conformément au périmètre technique. Ces exclusions et limites sont signalées dans le rapport.

Si une configuration locale remplace `scan.max_files_per_repo`, elle prend priorité sur le nouveau défaut : adapter ce réglage en fonction des rapports, sans augmenter aveuglément la limite.

## Réconciliation Audit / Diagnostic

La référence datée contenue dans `koa_ecosystem_diag/references/audit-inventory.20261110.json` provient du snapshot Audit fourni du 10 novembre 2026 et compte 49 dépôts. Le registre Diagnostic daté en compte 53, dont quatre absents de cette référence historique (`Karacter`, `Kolor`, `Kristalizer`, `diK`). Il ne s'agit **pas** d'une preuve que l'inventaire GitHub actuel est incomplet.

Le rapport privé `inventory-alignment.json` contient les différences. Pour utiliser ultérieurement un inventaire Audit plus frais, créer manuellement `koa-ecosystem-diag.audit-inventory.local.json` avec une liste `github_repos` de la forme :

```json
{"github_repos": ["Rejean-McCormick/Exemple"]}
```

L'inventaire local n'est **pas** fourni par l'overlay et reste sous ton contrôle.

## Compatibilité et limites

- Les 13 niveaux isolés LevelUpDiag, les rapports v2 et l'export privé `latest-audit.zip` restent présents.
- Le nouveau registre apparaît dans le bilan `coverage.boundary_registry`, sans jamais certifier l'E2E automatiquement.
- Le diagnostic ne démarre aucun test interne ni aucune application ; les sondes réseau restent opt-in.
- Un verdict `PARTIAL` est normal tant que des frontières obligatoires ou des preuves d'échanges ne sont pas complètement qualifiées.
- La v5.2 n'a pas encore été exécutée sur tes dépôts Windows réels ; les résultats de démonstration ne sont pas une validation de production.

## Tests

Depuis le root du dépôt Diag :

```powershell
py -3 -m unittest discover -s tests -v
```

Les rapports privés et la passerelle vers Audit restent dans `reports/Diagnostic-kOA-Digital-Ecosystem/`. Lorsqu'un rapport est exporté vers l'audit, seules des métadonnées agrégées et expurgées sont copiées.
