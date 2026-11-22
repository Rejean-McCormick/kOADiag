# kOADiag v5.4.1 · Validation intégrale

Extraire le ZIP à la racine de `C:\mycode\kOA_Digital_Ecosystem\kOADiag`. Le guide v5.4.0 fourni avec l’archive décrit l’installation des dépendances et les formats d’exports. Conserver les configurations locales, les décisions, les assets et `qualification-docs/` déjà présents.

## Un lancement

Ouvrir le lanceur Windows, garder la campagne **validation-integrale** sélectionnée et cliquer sur **Lancer la campagne**. La commande équivalente est la suivante.

```powershell
py Diagnostic-kOA-Digital-Ecosystem-CLI.py run validation-integrale --root C:\mycode
```

La campagne exécute les 15 niveaux. Elle ignore `execution.fail_fast` pour cette sélection. Un contrôle en échec garde son verdict et les contrôles indépendants continuent. Lorsqu’une donnée indispensable manque, les contrôles qui en dépendent indiquent `BLOCKED`. La matrice reste générée à partir des informations disponibles.

Les limites de collecte de cette campagne sont de 60 000 fichiers analysés par dépôt et 1 000 000 octets par fichier. Les exclusions de répertoires et d’extensions restent applicables. Consulter `scan-gaps.json` pour les omissions résiduelles. La collecte peut durer jusqu’à 30 minutes avant expiration.

Les résultats sont dans le dossier de campagne `runs/<identifiant>/`. Ouvrir `exports/validation-integrale.csv` pour filtrer les dépôts, frontières et modes. Le JSON `validation-integrale.json` fournit les motifs, les verdicts et les preuves. Les frontières reportées, écartées ou à revoir conservent leur statut. La campagne vérifie les exports déjà configurés pour les deux modes dans le même passage. Les données des deux modes doivent provenir de transactions distinctes et avoir été capturées avec le shell Koali dans l’état correspondant.

## Exécuter aussi le kit métier sur la pile locale d’essai

Cocher **Exécuter le kit Konnaxion–Orgo sur la pile locale d’essai** ou ajouter `--runtime-local`. Cette option exécute le kit PowerShell officiel du dépôt Orgo, qui crée des données d’essai dans Konnaxion et Orgo. La pile doit être préparée selon le README du kit, avec PowerShell 7, Docker et Orgo sur le port local 4000. Le diagnostic ne lance pas le script de préparation. Ajouter `--network` pour exécuter aussi les sondes GET/HEAD déjà activées dans la configuration.

```powershell
py Diagnostic-kOA-Digital-Ecosystem-CLI.py run validation-integrale --root C:\mycode --runtime-local --network
```

N14 rend le résultat des assertions du kit. Sa réussite ne démontre ni le mode Koali, ni la provenance de preuves externes. La qualification E2E par mode reste calculée à partir des exports des propriétaires. Les frontières sans kit, sans preuve ou sans prérequis conservent un résultat explicite dans la matrice. `latest-audit.zip` conserve son format d’export expurgé.

## Contrôles effectués

Les tests automatisés vérifient la poursuite de la campagne avec un registre invalide et `fail_fast=true`, la poursuite après l’échec d’une sonde, et la matrice pour les deux modes. La campagne a été exécutée sur les snapshots fournis et avec des transactions synthétiques séparées pour les deux modes. La recette Windows avec les services réels et le kit métier reste à faire sur le poste.
