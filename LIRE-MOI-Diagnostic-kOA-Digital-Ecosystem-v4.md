# Diagnostic du kOA Digital Ecosystem — v4.1

**Mission :** diagnostiquer les **relations entre les dépôts de l'écosystème**, et uniquement ces relations. C'est le diagnostiqueur transversal du kOA Digital Ecosystem ; il ne remplace ni les tests de chaque application ni LevelUpDiag dans un dépôt.

## Installer dans `C:\mycode`

Extraire le ZIP **à la racine `C:\mycode`** (et non dans un sous-dossier supplémentaire). Les nouveaux fichiers sont installés dans `C:\mycode\_KOA_OVERLAY_20261110\` :

- `Diagnostic-kOA-Digital-Ecosystem.pyw` : interface graphique Tkinter.
- `Lancer-Diagnostic-kOA-Digital-Ecosystem.cmd` : double-clic / lanceur Windows.
- `Diagnostic-kOA-Digital-Ecosystem-CLI.py` : terminal et automatisations.
- `koa_ecosystem_diag/` : scheduler, worker, niveaux, détecteurs et références.
- `koa-ecosystem-diag.manifest.json` : manifeste de 12 niveaux.
- `koa-ecosystem-diag.config.json` : configuration de base, **ne pas enregistrer de secrets**.
- `koa-ecosystem-diag.config.local.example.json` : modèle de configuration locale.

Le ZIP ne remplace pas `Diagnostic-InterRepo-Kernel.pyw` ni les autres versions antérieures.

### Démarrer

Double-cliquer sur `Lancer-Diagnostic-kOA-Digital-Ecosystem.cmd`, ou exécuter :

```powershell
py -3 "C:\mycode\_KOA_OVERLAY_20261110\Diagnostic-kOA-Digital-Ecosystem.pyw"
```

**Prérequis :** Python 3.10+ avec Tkinter. Bibliothèques utilisées : standard Python uniquement.

### CLI

```powershell
$cli = 'C:\mycode\_KOA_OVERLAY_20261110\Diagnostic-kOA-Digital-Ecosystem-CLI.py'
py -3 $cli run complet --root 'C:\mycode'
py -3 $cli run structure --root 'C:\mycode'
py -3 $cli run echanges --root 'C:\mycode'
py -3 $cli history --root 'C:\mycode'
```

La CLI retourne `0` pour PASS/WARN, `10` pour FAIL, `20` pour BLOCKED et `30` pour erreur diagnostic. Les écarts et preuves sont conservés même si la campagne échoue.

## Architecture adaptée de LevelUpDiag

L'implémentation reprend les contrats de l'archive `znapshot_LevelUpDiag_11101116.zip` :

```text
GUI / CLI
    ↓
Manifest LevelUpDiag v2 + config JSON
    ↓
Scheduler de campagne (DAG, depends_on, parallel_safe, max_parallel)
    ↓
1 processus Python neuf par niveau (timeout et exception isolés)
    ↓
Rapport par niveau (levelupdiag.report.v2, verdicts standardisés)
    ↓
Agrégation de campagne (levelupdiag.campaign-summary.v2)
    ↓
Historique runs / latest / fichiers de preuve
```

Les fichiers `koa_ecosystem_diag/schemas/` proviennent des schémas de l'archive LevelUpDiag fournie. Le scheduler est **adapté au diagnostic inter-repos**, et non une copie exécutable de l'application LevelUpDiag/Orgo : aucune suite de tests ni commande découverte n'est lancée.

## Niveaux spécialisés

| ID | Domaine | Ce qui est considéré comme preuve |
|---|---|---|
| N00 | Intégrité diagnostic | Inventaire/références lisibles, sécurité d'exécution |
| N01 | Collecte commune | Snapshot d'observations passives de frontière (53 dépôts inventoriés) |
| N02 | Topologie | Producteur/consommateur, dépôts présents, liaisons déclarées |
| N03 | Contrats IK & schémas | Descripteurs, versions, verrous SHA-256, `$ref` et dérive |
| N04 | Appels HTTP & routes | Appels sortants et correspondance de routes statiques |
| N05 | Événements | Couples publication/abonnement par topic exact |
| N06 | Dépendances | Manifestes et compatibilité de versions déclarées |
| N07 | Imports / CI / env | Imports, workflows inter-repos, **noms** de variables de service |
| N08 | Obligations | Fichiers/variables explicitement requis entre deux propriétaires |
| N09 | Traces / receipts | Corrélation d'exports émission-réception / IK |
| N10 | Sondes GET/HEAD | Contrôle réseau seulement si sonde et autorisation activées |
| N11 | Continuité | Synthèse par relation et **niveau de preuve**, jamais une E2E inférée |

Les niveaux N00/N01/N02/N03 constituent le socle ; les observations supplémentaires sont non obligatoires si leurs preuves ne sont pas configurées. Une obligation **explicite** en échec (`N08`) constitue un `FAIL`, même si son niveau est facultatif.

## Rapports

Par défaut :

```text
C:\mycode\_KOA_OVERLAY_20261110\reports\Diagnostic-kOA-Digital-Ecosystem\
  runs\<run-id>\
    summary.json
    summary.txt
    effective_config.json
    levels\N00\result.json ... levels\N11\result.json
    levels\N01\snapshot.json
    levels\N10\probes.json (si sondes activées et autorisées)
    exports\relations.csv, appels-api.csv, evenements.csv, ...
  latest\summary.json et levels\Nxx\result.json
```

Séparer les preuves **déclaratives**, **statiques**, **réponses de sondes** et **échanges corrélés** est volontaire : un HTTP 200 ne prouve pas que deux applications ont effectivement échangé une transaction métier.

## Déclarer des relations que l'analyse statique ne découvre pas

Ne pas modifier la configuration de base après installation. Copier le modèle `koa-ecosystem-diag.config.local.example.json` vers `koa-ecosystem-diag.config.local.json`, puis renseigner les écarts pertinents ; le fichier local est fusionné avec la base.

Exemple :

```json
{
  "interrepo": {
    "relations": [
      {"source": "Ekole", "target": "Kristal-Framework", "contract": "kristal.learning-surface", "status": "declared"}
    ],
    "boundary_expectations": [
      {"id": "ekole-kristal-boundary", "source": "Ekole", "target": "Kristal-Framework", "source_files": [], "target_files": []}
    ],
    "exchange_trace_files": [],
    "ik": {
      "trace_files": [],
      "probes": [
        {"id": "local-api-example", "enabled": false, "source": "Ekole", "target": "Kristal-Framework",
         "kind": "readiness", "method": "GET", "url": "http://127.0.0.1:8765/health",
         "expect_status": [200]}
      ]
    }
  }
}
```

**Important :** la valeur `boundary_expectations` ci-dessus est *illustrative et volontairement vide*. Définir au moins un fichier ou une référence de variable vérifiable avant d'activer cette obligation ; sinon elle génère un écart, à juste titre. Il n'y a aucun port de service deviné comme preuve d'échange.

Les chemins des exports de traces configurés doivent être relatifs à `C:\mycode`, et seront lus passivement. Les valeurs de variables d'environnement et les secrets ne sont pas collectés par le module des relations.

### Réseau

- Désactivé par défaut, même si des sondes sont déclarées.
- Une sonde doit avoir `enabled: true` **et** l'utilisateur doit cocher *Sondes API locales* ou passer `--network`.
- GET et HEAD seulement ; pas de POST, PUT, PATCH, DELETE, cookies, identifiants en URL, paramètres query ni redirections automatiques.
- Boucle locale seulement par défaut (`127.0.0.1`, `localhost`, `::1`).
- Accès distant requiert l'accord explicite dans l'UI, ou `--network --remote --ack-remote`.
- **Même un GET peut avoir des effets de bord sur un service mal conçu.** N'activer que les endpoints que l'on sait être en lecture seule.

## Limites

- Le snapshot fourni inventorie **53 dépôts**, mais ce nombre ne garantit pas qu'ils existent tous sur la machine.
- Les appels dynamiques, résolutions DNS, service mesh, messages chiffrés et intégrations non déclarées peuvent échapper à l'analyse statique.
- Un lien documenté ou un import détecté ne valide pas l'échange runtime ; les preuves de livraison doivent venir des traces des outils déjà existants.
- Le scan statique est borné (`scan.max_files_per_repo` / `max_file_bytes`) ; ces limites sont visibles dans le rapport.
- Aucun fichier de dépôt n'est modifié, aucune application n'est démarrée et aucun test métier n'est exécuté.

## Provenance

- Architecture : `znapshot_LevelUpDiag_11101116.zip`, principalement `docs/ARCHITECTURE.md`, `docs/LEVEL_CONTRACT.md`, `docs/RESULT_MODEL.md` et `schemas/`.
- Détection inter-repos : évolution du moteur livré dans `KOA_Interaction_Kernel_InterRepo_Diagnostic_v3.0.zip`.
- Topologie et inventaire : références issues des archives `Interaction-Kernel.zip` et `znapshot_kOA_Digital_Ecosystem_11100750.zip`.
