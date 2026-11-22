# kOADiag v5.6.0 — Centre de validation

## Objectif

Une seule première page pour choisir le niveau de validation, suivre la progression,
examiner les applications et les connexions puis récupérer les preuves. Les fonctions
LevelUpDiag existantes restent dans leurs onglets, avec leurs commandes et leurs rapports.

Cette organisation suit notamment UX-07 (parcours complets), UX-15 (parcours dominant)
et UX-18 (refondre sans perdre les capacités) du guide fourni.

## Première page : Centre de validation

- **Validation rapide totale** : lecture du registre C0, vérification des 21 ports actuellement attribués,
  signalement d'une identité de service incorrecte, inspection de toutes les paires déclarées,
  localisation des dépôts propriétaires connus. Aucun processus démarré, aucune API distante sondée.
- **Validation approfondie** : tous les contrôles rapides, points de santé HTTP configurés sur
  127.0.0.1 pour les services connus, et campagne LevelUpDiag `validation-integrale` en mode passif.
  Ne transmet ni `--runtime-local`, ni `--start-test-stack`, ni `--audit`, ni `--network`, ni `--remote`.
- **Vue d'ensemble** : synthèse, nombre de services, services essentiels, limites et suite logique.
- **Applications** : services C0 regroupés par système, statut par port, santé HTTP si applicable,
  double-clic pour les détails et lien vers les contrôles Ports C0 historiques.
- **Connexions** : extrémités locales Orgo/Konnaxion/Koali/Orgo Worlds ; détails accessibles.
  La paire « Audit kOA → HomePage » ne prétend plus être testée lorsque l'outil d'audit
  n'a pas son propre identifiant de service dans le registre.
- **Étapes et rapports** : étapes exécutées, résultat LevelUpDiag et chemin des rapports JSON/CSV/TXT.

## Fonctions conservées

Les onglets `Synthèse`, `Ports C0`, `Niveaux LevelUpDiag`, `Relations inter-repos`,
`Registre des frontières`, `Parcours E2E`, `Matrice de preuves`, `Exports de traces`,
`Constats et preuves`, `Historique` et `Journal d’exécution` ne sont pas supprimés.
Le bandeau de configuration des campagnes et les statistiques historiques réapparaissent
quand on ouvre ces onglets.

## Sécurité et statut

- **Service accessible** signifie TCP ouvert, pas « application fonctionnelle ».
- **Famille reconnue** n'est pas une preuve de l'instance exacte.
- **Connexions** : contrôle de présence des deux extrémités, pas de transaction IK.
- **E2E métier réel** : utilise toujours le parcours officiel de campagne à opt-in,
  qui peut lancer Docker et créer des données de test. Ne pas l'utiliser sans une
  base isolée et une vérification préalable. Il n'est pas lancé depuis les boutons rapides/approfondis.
- Les applications arrêtées volontairement sont signalées comme indisponibles, pas comme
  collision prouvée. Aucun port de remplacement n'est sélectionné.
- Les campagnes ne sont pas lancées en parallèle ; l'interface ne peut pas être fermée
  pendant le déroulement d'une validation centrale.

## Réports

Sous `reports/Diagnostic-kOA-Digital-Ecosystem/validations/<date-id>/` :

- `validation.json` : état consolidé avec provenance du registre.
- `applications.csv` : services C0, statuts et raisons.
- `connexions.csv` : extrémités et statut, sans fausse preuve E2E.
- `synthese.txt` : bilan lisible.

Pour la validation approfondie, le résultat renvoie aussi au rapport original de la
campagne LevelUpDiag, qui reste détenu et généré par son moteur existant.

## Limites et suite

Le Centre ne lance pas automatiquement les suites de tests **internes** de chaque
application, ni les agents distants, ni les tests E2E transactionnels. Leur orchestration
nécessite des adaptateurs propriétaires sûrs et une séparation claire des données de test.

Le registre C0 `config/local-dev-ports.v1.json` reste la source unique des ports.
