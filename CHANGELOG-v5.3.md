# Diagnostic du kOA Digital Ecosystem — v5.3 (grosse passe)

## Objectif

Passer du seul inventaire de frontières aux **preuves passives et vérifiables d'interactions inter-repos**, toujours sans exécuter les diagnostics internes des applications, sans mutation métier et sans conclure à une certification E2E globale.

## Modifications

- **13 niveaux LevelUpDiag conservés** : mêmes identifiants N00 à N12, workers isolés et scheduler.
- **Collecte ciblée étendue** : défaut `scan.max_files_per_repo` 8 500 → **12 000** et `max_file_bytes` 220 000 → **480 000**. Des fichiers ignorés et limites restantes sont explicitement reportés ; `*.local.json` a priorité sur ces valeurs par défaut.
- **Nouveau module `evidence_adapters.py`** : lecture passive JSON, JSONL ou NDJSON, avec alias de champs et `field_map` personnalisable. Support des exports `records`, `events`, `entries`. Les données métiers, tokens, URLs et identifiants de transaction bruts ne sont pas copiés dans les rapports.
- **Provenance déclarée des exports** : chaque fichier peut renseigner `owner_repo`. Pour une paire de preuves, l'émetteur et le récepteur doivent être représentés par des fichiers distincts attribués aux dépôts correspondants ; la réponse doit provenir du récepteur déclaré. Cette provenance n'est **pas une attestation cryptographique**.
- **Contrôle des preuves E2E renforcé** : une **même transaction corrélée** doit traverser tous les sauts, avec événements horodatés dans l'ordre, statut de réponse positif et fenêtre de fraîcheur configurable (7 jours par défaut). Des transactions indépendantes ne peuvent plus former un parcours certifié par erreur.
- **Registre actif** : les seules frontières HTTP *approuvées par une personne* et renseignées avec méthode et route deviennent des attentes explicites dans N04. Les frontières événementielles approuvées peuvent renseigner un canal, vérifié en N05.
- **Matrice des preuves par frontière** : nouveau `boundary-qualification.json` et `exports/matrice-preuves-frontieres.csv` ; aucune relation non revue n'obtient de verdict positif automatiquement.
- **Couverture localisable** : nouveau `exports/couverture-depots.csv`, avec limites et fichiers ignorés par dépôt.
- **Interface** : nouveaux onglets « Exports de traces » et « Matrice de preuves ». Ajouter/retirer/vérifier des exports depuis l'interface, en restant dans la racine choisie. Bouton « Déclarer un parcours » dans l'onglet Parcours E2E.
- **Passerelle GitHub Audit v0.22.0 préservée** : export des seules métadonnées, sans traces brutes.
- **Identité visuelle préservée** : logo fourni et `#1E6864`.

## Compatibilité et confidentialité

La configuration locale `koa-ecosystem-diag.config.local.json`, les décisions de registre `koa-ecosystem-diag.boundaries.local.json` et les historiques sont **exclus** de l'overlay. Ne pas publier les archives de preuve privées. Aucun scan ou sonde HTTP n'est lancé par le simple ajout d'un export : seules les campagnes lancées explicitement effectuent l'analyse.

## Limitations assumées

La présence de traces déclarées n'est pas une preuve inviolable de leur authenticité. Le statut `EVIDENCE_COMPLETE` s'applique **à un parcours déclaré et documenté**, jamais à tout l'écosystème. Le bilan global reste `NON_CERTIFIE` tant que le périmètre, les révisions et les preuves exhaustives ne sont pas officiellement qualifiés. Sans approbation humaine des frontières ou sans exports réels, les résultats restent `PARTIAL` / non prouvés.
