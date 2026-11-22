# Qualification documentaire des frontières kOA — 11 novembre 2026

**Autorité :** `/docs` du snapshot kOA Digital Ecosystem fourni, explicitement autorisé comme référence officielle. Toutes les décisions ci-dessous reflètent une **attente documentaire** ou un classement de périmètre; **aucune preuve réseau ou runtime n'a été produite**.

## Résultats

- Frontières examinées : **60**
- Approuvées comme relations attendues : **11** (obligatoires dans leur profil : **4**, optionnelles/conditionnelles : **7**)
- Différées, donc non qualifiées : **24**
- Écartées du périmètre inter-repos (étapes conceptuelles ou liens génériques redondants) : **6**
- À revoir : **19**

**Sens du mot APPROVED :** la relation/contrat doit être pris en compte dans le périmètre documentaire; **cela ne veut pas dire PASS E2E ni production déployée.** `required=true` veut dire obligatoire **dans le profil explicitement documenté**, jamais obligatoire pour chaque déploiement du kOA Digital Ecosystem.

## Frontières obligatoires documentées

- **Daat → Kristal-Framework** (`mapping`) : Référence /docs : Da’at effectue le mapping vers Kristal. Obligation dans le parcours historique v6 figé, pas une preuve d'exécution v10.
- **EncyKlopedia → Daat** (`mapping`) : Référence /docs : Handoff EncyKlopedia→Da’at du couloir v6 figé, conditionnel à ce profil historique.
- **Konnaxion → Orgo** (`governance.decision.execute/1.0.0`) : Référence /docs : Profil qualifié en runtime local intégré; obligatoire dans le parcours de décision Konnaxion↔Orgo.
- **Orgo → Konnaxion** (`accountability.impact.publish/1.0.0`) : Référence /docs : Impact publication qualifiée avec reçus terminaux et replay; obligatoire pour boucle Konnaxion↔Orgo.

## Parcours déclarés

- **Actif et exigé :** `konnaxion-orgo-decision-impact` (deux sauts et une même transaction au sens du moteur v5.3). Il sera **PREUVES_INSUFFISANTES** sans les exports propriétaires attendus.
- **Préparés, désactivés :** baseline EncyK v6, exports Orgo→Da’at, EncyK v2→Médiathèque C6, Authoring Kit→Manager→Konstellation Light, Skope→EncyK. La désactivation protège des faux verdicts lorsque l'identité transactionnelle ou la réception n'est pas qualifiée.
- Pas de parcours `UCKK` actif : la destination logique n'est pas un récepteur Git concret unique. Ne pas assimiler UCKK-Assets ou UCKK-Ops-Console à ce service sans preuve.

## Traces applicatives

Le `kOADiag.zip` fourni ne comporte aucun export `.jsonl`/`.ndjson` de transactions propriétaire. La configuration laisse `exchange_trace_files` intact (vide dans la base) et ne crée **aucune trace synthétique**.

Pour le parcours Konnaxion→Orgo→Konnaxion, fournir deux exports indépendants, produits respectivement par Konnaxion et Orgo, de préférence JSONL :

- `owner_repo` du fichier, identifiants `journey_id=konnaxion-orgo-decision-impact` et `correlation_id` commun aux deux sauts;
- `source_repo`, `target_repo`, `phase` (`sent`, `received`, `response`) et `timestamp` ISO8601 timezone-aware;
- pour chaque saut, un enregistrement d'émission, de réception et de réponse positive. Les exports sont en lecture seule, les payloads et secrets n'ont pas à être fournis.

Dans l'onglet **Exports de traces**, attribuer le fichier Konnaxion à `Konnaxion` et celui d'Orgo à `Orgo`. L'outil enregistre alors des chemins relatifs à `C:\mycode`. La documentation garantit la nature des contrats, **pas la génération de ces données**.

## Installation

1. Sauvegarder tout fichier existant `koa-ecosystem-diag.boundaries.local.json` ou `koa-ecosystem-diag.config.local.json` : ce ZIP les remplace explicitement. Le snapshot reçu contenait un registre à 60 frontières toutes `UNREVIEWED` et **aucune configuration `.local.json`**; ce package est adapté à **cet état fourni**.
2. Extraire **le contenu** de ce ZIP à la **racine kOADiag** où se trouve `Diagnostic-kOA-Digital-Ecosystem.pyw`, pas à `C:\mycode`.
3. Lancer la campagne `complet` après sauvegarde; vérifier le registre, l'onglet E2E, les preuves et les métriques. Aucun appel réseau n'est activé par cette configuration.
4. Les références sont recensées dans `qualification-docs/revue-60-frontieres.csv` et leurs SHA-256 dans `qualification-docs/sources-documentaires.sha256.json`.

## Limites

- L'archive `/docs` est une photographie datée, pas une interrogation GitHub live ni un dossier de contracts courants.
- Un `UNREVIEWED` ne signifie pas absence de communication; la preuve documentaire est insuffisante pour le qualifier.
- Un `REJECTED` exclut un **nœud conceptuel ou un doublon documentaire** du registre de communications entre dépôts; ne supprime aucun fichier source ni fonction applicative.
- Certaines liaisons documentées sont seulement candidates. Le mot *APPROVED* désigne un contrat **attendu dans le périmètre indiqué**, pas un état de qualification opérationnelle.
- L'export GitHub Audit reste séparé; aucun dépôt local n'est modifié par les vérifications de l'application.
