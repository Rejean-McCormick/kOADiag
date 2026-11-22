# Installation de kOA Digital Ecosystem Diagnostic v5.3 — OVERRIDE DIRECT ROOT

**Aucun patch Git, aucune commande `git apply`.** Tous les fichiers fournis sont des fichiers complets, avec leurs chemins relatifs à la racine du dépôt Diag.

## Installation

1. Fermer la fenêtre Diagnostic.
2. Faire une copie de sauvegarde des fichiers du dépôt Diag si tu y as apporté des changements locaux.
3. Ouvrir le dossier qui contient `Diagnostic-kOA-Digital-Ecosystem.pyw` et `koa_ecosystem_diag/`. C'est **le root du repo Diag**, pas `C:\mycode` sauf si l'application s'y trouve directement.
4. Extraire le **contenu** du ZIP directement dans cette racine en acceptant la fusion des dossiers et le remplacement des fichiers communs.
5. Garder les deux fichiers privés existants : `koa-ecosystem-diag.config.local.json` (réglages et chemins d'exports) et `koa-ecosystem-diag.boundaries.local.json` (revues humaines). **Ils ne figurent pas dans le ZIP.** Les campagnes historiques ne sont pas incluses non plus.
6. Lancer `py -3 "C:\mycode\kOA_Digital_Ecosystem\kOADiag\Diagnostic-kOA-Digital-Ecosystem.pyw"` en adaptant le chemin si ton repo est ailleurs. Ou utiliser le lanceur CMD existant.
7. Tester le code : `py -3 -m unittest discover -s tests -v` depuis le dossier Diag.

Python 3.10+ avec Tkinter est nécessaire. Aucun `pip install` requis.

## Nouveau flux de qualification

1. Lancer `complet`, puis ouvrir **Registre des frontières**. Approuver explicitement chaque frontière importante et choisir son caractère obligatoire/optionnel.
2. Pour HTTP, préciser **méthode et route**. Pour EVENT, préciser **canal**. Les engagements approuvés seront contrôlés statiquement dès la prochaine campagne. Un appariement statique ne démontre pas un appel réussi.
3. Ouvrir **Exports de traces**. Ajouter des fichiers JSON/JSONL/NDJSON de diagnostics *existants*, sous la racine des dépôts, et préciser le dépôt réellement producteur de chaque fichier. Le diagnostic ne lance pas ces outils.
4. Pour un format personnalisé, ajouter un `field_map` à l'objet d'export dans `koa-ecosystem-diag.config.local.json`. Une source peut par exemple être :

```json
{
  "path": "Konnaxion/Konnaxion/exports/interaction.jsonl",
  "owner_repo": "Konnaxion",
  "field_map": {
    "correlation_id": "context.trace_id",
    "source_repo": "source",
    "target_repo": "target",
    "phase": "phase",
    "timestamp": "observed_at"
  }
}
```

Ceci est un exemple **à adapter à tes fichiers réels**. Les chemins et noms de champs doivent correspondre à tes exports ; aucune cible n'est inventée.

5. Dans **Parcours E2E**, cliquer sur **Déclarer un parcours** et fournir un identifiant stable puis la chaîne des dépôts (`A, B, C`). Sans preuves réelles, ce parcours restera non prouvé.
6. Relancer `complet` (ou `e2e`) pour lire les preuves et examiner **Matrice de preuves** et **Parcours E2E**.

### Contrat minimal d'une trace

Chaque ligne JSONL ou objet JSON décrit une **observation de frontière** :

- `correlation_id` : identifiant partagé par **tous les sauts** de la même transaction ;
- `journey_id` : identifiant du parcours déclaré ;
- `source_repo`, `target_repo` : dépôts à la frontière ;
- `phase` : `sent`, `received`, `response` (ou `published`, `consumed`) ;
- `method` et `path` si HTTP ;
- `status` de la réponse (p. ex. HTTP 200) ;
- `timestamp` : date ISO 8601 avec fuseau/UTC, assez fraîche pour la politique de preuve.

Les phases d'une frontière doivent apparaître dans **des exports distincts** émis par les dépôts appropriés : source pour `sent`, destination pour `received` et `response`. Les horodatages doivent être cohérents et les réponses réussies. Une sonde HTTP, une route trouvée ou un contrat présent ne remplissent pas ces conditions.

### Paramètres de contrôle de fraîcheur

Le fichier par défaut inclut :

```json
"evidence_policy": {"require_timestamps": true, "max_age_hours": 168}
```

La configuration locale peut ajuster `max_age_hours` (entre 1 et 8760). Garder `require_timestamps=true` pour une qualification fiable.

## Rapports privés

Sous `reports/Diagnostic-kOA-Digital-Ecosystem/runs/<RUN_ID>/` :

- `summary.json` et `summary.txt` : vue LevelUpDiag et priorités ;
- `registry-snapshot.json` : état des décisions à la date de la campagne ;
- `boundary-qualification.json` : matrice de qualification des observations ;
- `exports/matrice-preuves-frontieres.csv` : qualification par frontière ;
- `exports/couverture-depots.csv` : dépôt manquant, tronqué, fichiers ignorés ;
- `levels/N01/snapshot.json` : preuves techniques résumées, sans payloads ;
- `bridge-audit/latest-audit.zip` : export privé filtré pour **GitHub Audit v0.22.0** (sous `reports/Diagnostic-kOA-Digital-Ecosystem/bridge-audit/`, pas dans le run).

**Ne pas committer ni publier ces fichiers de preuve.** Ils peuvent révéler des chemins et l'architecture interne même sans données métier.

## Vérification de la version

La fenêtre affiche **v5.3**, le manifest indique **5.3.0** et les 13 niveaux N00 à N12 restent présents.

## Ce que ce diagnostic n'affirme pas

Une transaction observée via des exports reste susceptible de logs incomplets, falsifiés ou non authentifiés. `EVIDENCE_COMPLETE` signifie **preuves passives cohérentes pour le parcours déclaré**. Le diagnostic ne certifie jamais automatiquement la totalité de l'écosystème ou la sécurité de chaque application.
