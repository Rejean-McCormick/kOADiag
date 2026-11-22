# Recette finale du Diagnostic kOA

La campagne Windows reçue en v5.4.0 a détecté les 53 dépôts. Sur quatre frontières obligatoires, deux étaient dans un parcours déclaré et aucune n’était corroborée. Aucune trace ni reçu exploitable n’était importé. La dernière campagne reçue comportait deux dépôts touchés par les limites de collecte. La campagne intégrale relève ces limites et identifie ce qui reste hors collecte.

## Une campagne après la préparation des preuves

1. Extraire cet override à la racine de `C:\mycode\kOA_Digital_Ecosystem\kOADiag`. Conserver les fichiers locaux et les décisions.
2. Exécuter la boucle métier Konnaxion → Orgo → Konnaxion une fois avec le shell Koali arrêté, puis avec Koali actif. Les deux propriétaires exportent les émissions, réceptions et réponses terminales avec la même corrélation dans une transaction. Utiliser une nouvelle corrélation dans l’autre mode. Les journaux et le résumé Koali peuvent compléter ces exports. Voir les formats et l’exemple dans le guide v5.4.0.
3. Résoudre le périmètre du couloir historique EncyKlopedia → Daat → Kristal-Framework. Le registre actuel le marque obligatoire pour la baseline figée. Obtenir auprès des propriétaires le schéma versionné du handoff `encyklopedia.corpus-harvest-handoff/1.0.0`, ainsi que les captures du parcours. La référence figée `kristal_state/6.0.0` est contrôlée par comparaison des schémas et du verrou. Le profil IK `kristal.build.request/2.0.0` n’admet que Konnaxion et Orgo comme émetteurs dans le snapshot. Si le couloir historique ne s’applique plus au périmètre visé, faire acter cette décision et mettre à jour le plan documentaire avant la revue finale.
4. Lancer **validation-integrale** une fois depuis l’interface, ou depuis PowerShell.

```powershell
py Diagnostic-kOA-Digital-Ecosystem-CLI.py run validation-integrale --root C:\mycode
```

Sur une pile locale d’essai déjà préparée, l’option `--runtime-local` exécute également les assertions métier du kit Konnaxion–Orgo, avec création de données de test. Lancer ce kit et consigner les preuves par mode sont des contrôles distincts. Le guide v5.4.1 décrit ses prérequis.

## Lecture et clôture

- Ouvrir `cloture.txt` pour les compteurs par mode et `cloture.json` pour les contrôles obligatoires restants, les causes et les sauts concernés. Ces fichiers sont disponibles dans le dossier de campagne et dans `latest/`. Pour une revue à distance, transmettre le seul `cloture.json` de la campagne intégrale.
- Utiliser `scan-gaps.json` si un dépôt reste partiellement couvert, et `exports/validation-integrale.csv` pour filtrer tous les résultats. Une relation optionnelle ou une décision ouverte figure séparément des obligations en échec.
- Vérifier l’interface et les assets sous Windows, puis importer `bridge-audit/latest-audit.zip` dans GitHub Audit v0.22.0. Vérifier l’identifiant de campagne et les verdicts. Le rapport de clôture demeure local et l’export Audit conserve son format expurgé.
- Une seconde campagne est utile si des preuves ou des prérequis ont changé après la première. Reprendre d’abord les contrôles signalés dans le rapport. La revue humaine entérine la clôture et le périmètre retenu.
