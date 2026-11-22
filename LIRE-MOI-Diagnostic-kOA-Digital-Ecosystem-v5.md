# Diagnostic du kOA Digital Ecosystem — v5.0

**Identité :** Diagnostic du kOA Digital Ecosystem, logo UCKK fourni, couleur `#1E6864`.

**Mission inchangée :** auditer **les relations entre dépôts** : appels API, routes exposées, versions de contrats, messages, dépendances, imports, configuration, CI, Interaction Kernel, traces émission/réception et parcours déclarés. Aucun test interne des applications, aucune commande d'installation, aucun lancement de service, aucune migration.

## 1 — Installer dans C:\mycode

Extraire le contenu du ZIP à la racine `C:\mycode`, et fusionner le dossier `_KOA_OVERLAY_20261110`.

- `Diagnostic-kOA-Digital-Ecosystem.pyw` — interface graphique Tkinter.
- `Lancer-Diagnostic-kOA-Digital-Ecosystem.cmd` — lanceur Windows.
- `Diagnostic-kOA-Digital-Ecosystem-CLI.py` — CLI et automatisation.
- `koa_ecosystem_diag/` — moteurs statiques, preuves, scheduler, workers, schémas, références.
- `koa-ecosystem-diag.manifest.json` — 13 niveaux LevelUpDiag.
- `koa-ecosystem-diag.config.json` — paramètres par défaut.
- `koa-ecosystem-diag.config.local.example.json` — modèle pour votre personnalisation.
- `assets/` — logo SVG d'origine et versions PNG pour Tkinter.
- `tests/` — tests unitaires de logique de preuve.

Le ZIP **ne contient pas** `koa-ecosystem-diag.config.local.json` et ne remplace donc pas vos paramètres locaux déjà personnalisés. Une v4 installée dans le même dossier sera remplacée pour les fichiers communs. Conserver au besoin une copie préalable du dossier avant extraction. Les résultats historiques ne sont pas inclus, effacés, ni réécrits.

Prérequis : Python 3.10+ avec Tkinter. Aucun `pip install` nécessaire. Lancer par double-clic sur le `.cmd` ou :

```powershell
py -3 "C:\mycode\_KOA_OVERLAY_20261110\Diagnostic-kOA-Digital-Ecosystem.pyw"
```

## 2 — La correction majeure : un scan PARTIAL ne bloque plus toute la campagne

Ancienne v4 : N01 `PARTIAL` était traité comme un échec fatal, ce qui mettait 10 niveaux dépendants en `BLOCKED` malgré l'existence d'un snapshot exploitable. **Désormais :**

- Un prérequis `PARTIAL` permet aux workers suivants de poursuivre sur la partie observée.
- Chaque worker dépendant reçoit une constatation `evidence.upstream.partial` avec le verdict `PARTIAL`, en plus de ses propres constats.
- Un prérequis `FAIL`, `BLOCKED`, `ERROR`, `INFRA_ERROR`, `CONFIG_ERROR` ou `SKIP` reste bloquant.
- Le verdict de campagne est `PARTIAL` si un niveau obligatoire est partiel, plutôt que `BLOCKED` par simple manque de couverture.
- Les échecs réellement constatés restent des `FAIL` : rien n'est artificiellement verdi.

La limite de fichiers inspectés passe par défaut de **900 à 3500 par dépôt**, avec plafond de sécurité et configurabilité locale. Les scans encore tronqués restent signalés et rendent la couverture partielle.

## 3 — Les 13 niveaux spécialisés

| Niveau | Périmètre |
|---|---|
| N00 | Références, inventaire et sécurité |
| N01 | Collecte passive, surfaces de frontière et couverture |
| N02 | Graphe producteur/consommateur et présence des dépôts |
| N03 | IK, schémas, `$ref`, verrous et versions |
| N04 | Appels HTTP, routes, frontières API explicites |
| N05 | Événements, producteurs et abonnés |
| N06 | Dépendances et contraintes de versions |
| N07 | Imports croisés, références CI et noms de variables de service |
| N08 | Obligations déclarées sur chaque frontière |
| N09 | Exports passifs émission/réception et reçus IK |
| N10 | Sondes GET/HEAD **opt-in**, locales ou distantes avec accord explicite |
| N11 | Continuité documentaire et degré de preuve de chaque liaison |
| **N12** | **Parcours E2E explicitement déclarés, vérifiés saut par saut** |

Campagnes : `complet`, `structure`, `echanges`, **`e2e`**. Le scheduler applique les dépendances déclarées dans le manifeste, lance chaque niveau en processus Python distinct, conserve ses traces d'erreur et impose un timeout.

## 4 — Qualification E2E : une preuve, pas une supposition

**Le diagnostic global « A à Z » reste `NON_CERTIFIE` tant qu'il n'existe pas un référentiel exhaustif de parcours et des preuves fiables de chacune de leurs frontières.** Le niveau N12 peut indiquer `EVIDENCE_COMPLETE` pour **un parcours configuré**, sans certifier pour autant l'ensemble des 53 dépôts.

Pour chaque saut `A → B`, N12 requiert par défaut :

1. Une émission et une réception avec le **même `correlation_id`**.
2. Un **`journey_id` identique** sur les sauts du même parcours déclaré.
3. Une réponse positive corrélée, `status` HTTP `2xx` ou `success` / `ok` / `succeeded` / `accepted`.
4. Des preuves côté émetteur et côté récepteur issues de **fichiers d'export différents**.

Les IDs sont hachés dans le rapport. Les corps des messages, mots de passe et jetons ne sont pas recopiés. Cette corroboration atteste la cohérence des **exports fournis** ; elle ne remplace ni leur chaîne de confiance ni les tests métiers. Une simple réponse de sonde HTTP 200 ne compte jamais comme transaction inter-repos E2E.

### Déclarer un parcours

Créer ou ouvrir dans l'UI (`CONFIG E2E`) :

`C:\mycode\_KOA_OVERLAY_20261110\koa-ecosystem-diag.config.local.json`

Exemple, **à activer uniquement lorsque les exports correspondants existent** :

```json
{
  "interrepo": {
    "journeys": [
      {
        "id": "konnaxion-orgo-retour",
        "enabled": true,
        "required": true,
        "nodes": ["Konnaxion", "Orgo", "Konnaxion"],
        "require_response": true
      }
    ],
    "exchange_trace_files": [
      "diagnostics/exports/konnaxion-send.jsonl",
      "diagnostics/exports/orgo-receive.jsonl",
      "diagnostics/exports/response.jsonl"
    ]
  }
}
```

Tous les chemins de traces sont relatifs à `C:\mycode`. Les fichiers de cet exemple sont **fictifs** : adapter les chemins aux vrais exports des diagnostics dédiés.

Format attendu, **une ligne JSON par phase** (ou tableau `.json` équivalent) :

```json
{"correlation_id":"id-de-transaction","journey_id":"konnaxion-orgo-retour","source_repo":"Konnaxion","target_repo":"Orgo","phase":"sent","method":"GET","path":"/boundary"}
{"correlation_id":"id-de-transaction","journey_id":"konnaxion-orgo-retour","source_repo":"Konnaxion","target_repo":"Orgo","phase":"received","method":"GET","path":"/boundary"}
{"correlation_id":"id-de-transaction","journey_id":"konnaxion-orgo-retour","source_repo":"Konnaxion","target_repo":"Orgo","phase":"response","method":"GET","path":"/boundary","status":"200"}
```

Ces lignes doivent se trouver dans les exports appropriés (émetteur et récepteur séparés) pour justifier leur indépendance. Pour le deuxième saut, utiliser un autre identifiant de corrélation et les mêmes `journey_id`, mais `source_repo: Orgo`, `target_repo: Konnaxion`. Ne pas injecter de fausses traces pour obtenir un PASS.

## 5 — Frontières API attendues (nouveau)

Dans la configuration locale, définir les frontières API importantes, sans supposer les ports ou les hôtes :

```json
{
  "interrepo": {
    "expected_api_links": [
      {"id":"konnaxion-orgo-readiness","enabled":true,"required":false,
       "source":"Konnaxion","target":"Orgo","method":"GET","path":"/health/ready/"}
    ]
  }
}
```

N04 cherche **un appel sortant** dans le code du dépôt source et **une route entrante** dans le code du dépôt cible. Les résultats possibles sont `APPEL_ET_ROUTE_STATIQUES`, `APPEL_SANS_ROUTE_OBSERVEE`, `ROUTE_SANS_APPEL_OBSERVE`, `NON_OBSERVE`, `CONFIG_INVALIDE`. Les routes dynamiques ou découvertes à l'exécution peuvent échaper à l'analyse : l'absence statique déclenche une revue, pas un faux verdict de panne runtime. Les nouvelles colonnes sont exportées en CSV.

Une correspondance de route ne prouve **pas** que l'appel a réellement été émis ni reçu.

## 6 — Gestion des schémas : moins de faux positifs

- Les références `$ref` URN (`urn:...`) ou à schéma d'URI externe ne sont plus traitées par défaut comme des fichiers relatifs manquants.
- Deux fichiers avec le même `$id` mais des empreintes différentes sont classés `SCHEMA_ID_MULTIPLE_DIGESTS_REVIEW`, **à qualifier**, plutôt qu'incompatibles sans preuve de verrou de version.
- Seuls les vrais schémas (`*.schema.json`, chemins `schemas/`, OpenAPI) sont traités en tant que tels. Une configuration comme `schema-endpoints.json` dans un répertoire applicatif n'est plus qualifiée automatiquement de schéma.
- Les dérives de contrats ou de locks IK explicitement vérifiées restent signalées par leurs contrôles propres.

## 7 — Rapports, historique, priorité

Sortie par défaut :

`C:\mycode\_KOA_OVERLAY_20261110\reports\Diagnostic-kOA-Digital-Ecosystem\runs\<run-id>\`

- `summary.json`, `summary.txt` : résultats, couverture, verdict LevelUpDiag, non-certification E2E globale.
- `levels/Nxx/result.json` et `levels/N01/snapshot.json` : preuve par niveau, métriques et source.
- `exports/matrice-relations.csv` : **matrice inter-repos** (topologie, contrats, API, reçus, obligations).
- `exports/frontieres-api.csv`, `exports/routes-api.csv`, `exports/parcours-e2e.csv`, autres CSV spécialisés.
- `priorites.txt` : actions de qualification qui manquent concrètement.
- `delta.json` : comparaison avec la campagne précédente (différences de couverture et d'état du graphe).
- `latest/` : résumé et verdicts des niveaux les plus récents.

L'interface comporte sept onglets : **Synthèse**, Niveaux LevelUpDiag, Relations inter-repos, **Parcours E2E**, Constats et preuves, Historique, Journal. Elle conserve le logo et la couleur `#1E6864`.

## 8 — CLI

```powershell
$cli='C:\mycode\_KOA_OVERLAY_20261110\Diagnostic-kOA-Digital-Ecosystem-CLI.py'
py -3 $cli run complet --root 'C:\mycode'
py -3 $cli run structure --root 'C:\mycode'
py -3 $cli run e2e --root 'C:\mycode'
py -3 $cli history --root 'C:\mycode'
```

Codes de sortie : PASS/WARN `0`, FAIL `10`, BLOCKED `20`, **PARTIAL `21`**, erreur d'infrastructure `30`.

## 9 — Sécurité et limites

- Lecture seule sur les dépôts ; seules les preuves et rapports sont écrits dans le dossier du diagnostiqueur.
- Aucune app n'est démarrée, aucune suite interne lancée, aucune modification de code, aucun `git` mutateur.
- Sondes réseau désactivées par défaut ; seuls GET/HEAD sont autorisés sur endpoints opt-in explicitement configurés. La sonde locale requiert une case cochée ou `--network`, la distante nécessite une confirmation supplémentaire.
- Les traces sont lues **passivement** ; les champs identifiants sont hachés. Une preuve exportée peut rester erronée ou altérée si la source n'est pas fiable.
- Les communications dynamiques, bus de messages, RPC, versions résolues en exécution ou intégrations non déclarées peuvent échapper à la lecture statique.
- Aucun test individuel d'application n'est effectué : c'est précisément la mission de tes diagnostics dédiés.
- Un projet entièrement vert dans ses tests internes n'implique pas que tous ses contrats externes soient compatibles.

### Provenance

Architecture adaptée depuis le snapshot LevelUpDiag fourni ; cartographie issue des références kOA et Interaction Kernel fournies précédemment. **Les résultats du ZIP de campagne v4 du 10 novembre 2026 constituent un point de départ, et non une certification réutilisable sur la v5.**
