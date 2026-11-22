# kOA Digital Ecosystem Diagnostic v5.3.1 — Correctif inter-repos

## Installation root-ready

Extraire **le contenu** de ce ZIP à la **racine du dépôt kOADiag**, c'est-à-dire
là où se trouve `Diagnostic-kOA-Digital-Ecosystem.pyw`. Fusionner/remplacer les
fichiers existants. C'est un override de **fichiers COMPLETS**, jamais un patch.

Ne PAS extraire à `C:\mycode` si le dépôt est dans un sous-dossier. Fermer
l'application avant remplacement. Aucune configuration `*.local.json`, aucune
trace privée, aucun registre humain, aucun historique ne sont inclus.

## Corrections apportées

1. `required_in_journey` compte la **déclaration du parcours actif** et
   `required_proven` ne compte que les parcours effectivement corroborés.
   Ajout de `required_without_journey` et `required_declared_unproven`.
2. Association **exacte du contrat IK par saut** via `journeys[*].contract_refs`.
   Une autre relation Konnaxion→Orgo ne peut pas hériter de la qualification.
3. Les preuves importées peuvent exposer `contract` ou `contract_id` (ou être
   mappées via `field_map`). Le profil doit correspondre sur les exports de
   l'émetteur et du récepteur **et** au contrat du parcours pour valider un
   saut au titre de ce profil. Un export sans contrat demeure une observation,
   sans être attribué par défaut à un profil IK.
4. Nouveau `scan-gaps.json` : par dépôt, comptes par dossier de premier niveau
   pour les fichiers non sélectionnés et trop volumineux, sans contenu source.
   `exports/couverture-depots.csv` inclut `unselected_files` et
   `index_overflow_files`. Le plafond de scan n'est PAS relevé aveuglément.
5. L'UI différencie frontières obligatoires dans un parcours et frontières
   réellement prouvées. Architecture LevelUpDiag, 13 niveaux, branding et
   export GitHub Audit préservés.

## État de départ établi sur la campagne 20261111T145649Z-df900489

- 53/53 dépôts présents ; verdict PARTIAL ; 0/1 parcours corroboré ;
- 4 frontières APPROVED/required : deux dans le parcours actif
  Konnaxion→Orgo→Konnaxion, deux sans parcours actif
  (EncyKlopedia→Daat et Daat→Kristal-Framework) ;
- Kristalizer : 44 933 fichiers éligibles / 11 336 analysés ; 664 trop volumineux ;
- kristal-public : 244 trop volumineux ; Konductor : zéro fichier éligible ;
- 0 export de traces configuré. **Aucun résultat de communication E2E prouvé.**

Le correctif a été testé sur ce snapshot existant : `required_in_journey=2`,
`required_without_journey=2`, `required_unproven=4`, `required_proven=0`.
Ces nombres ne sont pas une nouvelle campagne runtime.

## Test et campagne

Dans la racine du dépôt :

```powershell
py -3 -m unittest discover -s tests -p 'test_*.py' -v
py -3 'Diagnostic-kOA-Digital-Ecosystem.pyw'
```

Lancer ensuite la campagne `complet`. Regarder dans le dossier de campagne :

- `boundary-qualification.json` et `exports/matrice-preuves-frontieres.csv`
- `scan-gaps.json` et `exports/couverture-depots.csv`
- `levels/N01/snapshot.json`, `summary.json`, `levels/N12/result.json`

## Les preuves encore nécessaires

**Ce ZIP ne fournit aucune preuve runtime.** Voir `GUIDE_PREUVES_KONNAXION_ORGO.md`
pour les métadonnées à exporter des diagnostics dédiés. Le système ne
sera pas marqué E2E certifié tant que les preuves ne sont pas présentes.

Ne pas publier les archives brutes sur GitHub Pages : chemins, noms de services
et métadonnées peuvent être sensibles. L'export Audit expurgé reste distinct.
