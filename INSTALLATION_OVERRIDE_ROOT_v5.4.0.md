# Diagnostic du kOA Digital Ecosystem v5.4.0

## Installation Windows

Extraire le ZIP directement dans `C:\mycode\kOA_Digital_Ecosystem\kOADiag` et accepter le remplacement des fichiers applicatifs. Les fichiers `*.local.json`, le registre de décisions, les dossiers de rapports et les assets présents restent sur le poste. Les deux PNG attendus par l’interface sont `assets/uckk-logo-header.png` et `assets/uckk-logo-64.png`. Les snapshots ne contenaient aucun de ces PNG. Conserver la copie locale de ces assets.

Dans PowerShell, depuis la racine du diagnostic, utiliser le même interpréteur pour l’installation et les campagnes.

```powershell
py -m pip install -r requirements-diag-v5.4.txt
py -m unittest discover -s tests -v
py Diagnostic-kOA-Digital-Ecosystem-CLI.py run complet --root C:\mycode
```

Lancer l’interface avec `Lancer-Diagnostic-kOA-Digital-Ecosystem.cmd` ou ouvrir `Diagnostic-kOA-Digital-Ecosystem.pyw`. Le cœur nécessite Python 3.10 ou plus et l’interface nécessite Tkinter. Pour importer les enveloppes et reçus IK natifs via `interrepo.ik.trace_files`, installer le runtime Python officiel depuis le checkout de confiance, avec Python 3.11 ou plus.

```powershell
py -m pip install C:\mycode\Interaction-Kernel\interaction_kernel\runtime\python
```

Les références de qualification déjà installées dans `qualification-docs/` doivent être présentes. Le diagnostic utilise `sources-documentaires.sha256.json` et `plan-preuves-obligatoires.csv` pour rapprocher la campagne du plan de référence. Le bouton **Rapprocher le dernier scan** inscrit les observations nouvelles dans le registre sur action explicite. Une campagne écrit ses propres résultats et sa copie du registre dans les rapports.

## Utilisation et architecture

- **N00–N01.** L’inventaire prend les références `docs/inventory` locales disponibles, puis utilise les références embarquées en secours. N01 collecte en lecture seule et produit `documentary-scope.json`, `scan-gaps.json`, `registry-snapshot.json`, ainsi que la matrice CSV et JSON. Une collecte partielle reste utilisable par les autres workers. Les omissions recensent la taille, la lecture, les budgets de scan ou le plafond d’indices par surface. Le rapport donne jusqu’à 1 000 entrées de détail par dépôt avec le total correspondant. Les chemins précis peuvent être priorisés dans `interrepo.boundary_expectations`.
- **N02–N08.** Les correspondances de route utilisent l’identité du service configurée, le schéma URL, le port, la méthode et le chemin. Un nom d’hôte seul constitue un indice. Un topic commun constitue une correspondance statique. N03 vérifie l’index officiel, les descripteurs et schémas JSON, le sens producteur/récepteur et les six empreintes du verrou adopté Konnaxion–Orgo. Les trois profils de cette frontière appartiennent à l’index actif de 11 profils du snapshot.
- **N09–N12.** Les exports d’émission, de réception et de réponse sont comparés par transaction, tentative, frontière, contrat, méthode, route ou canal et mode. Une réponse `202` ou `accepted` reste une acceptation en attente en qualification stricte. Les fichiers doivent provenir des propriétaires attendus, fournir des horodatages ordonnés et respecter la fraîcheur configurée. Les sorties de diagnostic spécialisées, les journaux du Broker et les reçus natifs kOA Linux donnent des observations complémentaires. L’identité du journal, le nombre de lignes, la séquence et le SHA-256 des lignes sont vérifiés. Les reçus Linux sont validés avec les schémas du dépôt kOA Linux. Une corrélation commune au journal ou au reçu est affichée en complément d’un échange.
- **Mode autonome.** Déclarer `autonome` pour des transactions effectuées directement par les services propriétaires, avec les dépendances techniques dont ils ont besoin. Le diagnostic ne lance aucun shell Koali. Vérifier sur le poste que le shell est effectivement arrêté et garder les preuves de l’état de l’environnement.
- **Mode intégré.** Déclarer `integre` pour des transactions sous orchestration Koali. Un `koali-summary` peut corroborer la campagne Koali et son niveau N12. Les preuves de transaction proviennent des services concernés. Les dépendances statiques au shell sont indiquées comme indices. L’orchestration réellement utilisée doit être documentée lors de la capture.
- **Matrice.** Le statut documentaire, la validation du contrat, les paires observées, les preuves E2E et le verdict disposent de champs distincts. Les obligations du plan absent du registre sont signalées dans `documentary-scope.json`. Les lignes approuvées dont les dépôts sont absents restent visibles. Les rapports indiquent le périmètre obligatoire couvert, par mode. La certification globale reste non accordée par le diagnostic.
- **Audit.** `reports/Diagnostic-kOA-Digital-Ecosystem/bridge-audit/latest-audit.zip` contient les métadonnées expurgées selon le contrat d’export v0.22. Une copie par identifiant de campagne et une somme SHA-256 reproductible via `export-audit` sont disponibles. Utiliser uniquement cet export prévu pour Audit.

## Migration des configurations locales

Le fichier `koa-ecosystem-diag.config.local.example.json` illustre les paramètres de base. Fusionner les entrées voulues dans la configuration locale existante. Les listes sont remplacées par le chargement de configuration. Conserver les autres éléments de `journeys`, `exchange_trace_files` et des listes déjà utilisées.

Exemple d’extrait pour une campagne autonome. Utiliser les SHA-256 obtenus à partir d’une source de confiance et comparer les révisions exactes avec celles déployées. L’identifiant de parcours doit correspondre au champ `journey_id` des preuves et être unique dans la configuration. Une campagne intégrée distincte peut être déclarée avec un autre identifiant de parcours et des exports capturés en mode `integre`.

```json
{
  "interrepo": {
    "evidence_policy": {"mode": "autonome", "strict_evidence": true, "max_age_hours": 168},
    "journeys": [{
      "id": "konnaxion-orgo-decision-impact-autonome",
      "nodes": ["Konnaxion", "Orgo", "Konnaxion"],
      "contract_refs": [
        "governance.decision.execute/1.0.0",
        "accountability.impact.publish/1.0.0"
      ],
      "required": true,
      "mode": "autonome",
      "require_response": true
    }],
    "exchange_trace_files": [
      {"path": "preuves/konnaxion.jsonl", "owner_repo": "Konnaxion", "mode": "autonome", "sha256": "REMPLACER"},
      {"path": "preuves/orgo.jsonl", "owner_repo": "Orgo", "mode": "autonome", "sha256": "REMPLACER"},
      {"path": "preuves/broker.jsonl", "owner_repo": "kOA-Linux-Koali", "format": "koa-linux-journal", "mode": "autonome"}
    ]
  }
}
```

Un enregistrement de frontière comporte `correlation_id`, `journey_id`, `attempt_id`, `source_repo`, `target_repo`, `contract`, `phase`, `timestamp`, `source_revision` et `target_revision`. Les champs `method` et `path` précisent HTTP. `channel` identifie le canal événementiel. La phase est `sent`, `received`, `response`, `published` ou `consumed`. Une réponse terminale fournit `status`. Pour associer une réponse à un événement, reprendre le même canal. Pour des exports dont les noms de champs diffèrent, configurer `field_map`. Un chemin doit être relatif à `C:\mycode`.

Une révision est le SHA Git complet du checkout ou la révision renseignée dans `evidence_policy.reference_revisions` pour un snapshot ou checkout sans HEAD lisible. HEAD représente le commit et le diagnostic ne vérifie pas la propreté de l’arbre de travail. La correspondance des SHA-256 protège l’intégrité des octets. L’attribution de la source et l’état du déploiement doivent être contrôlés par l’opérateur.

Les formats complémentaires sont `koa-linux-receipt`, `koa-linux-journal`, `koali-summary`, `orgo-summary` et `konnaxion-summary`. Pour les trois derniers, indiquer le `summary.json` du diagnostic propriétaire. Les adaptateurs ingèrent ces rapports et n’exécutent aucune suite spécialisée. Un export natif ne contenant pas les phases et identités requises ne peut pas remplacer les preuves des deux propriétaires.

## Recette sur le poste pour la v6.0

1. Vérifier les dépôts réellement installés, leurs révisions et les écarts de collecte, notamment Kristalizer. Confirmer le périmètre documentaire actuel et l’identité de chaque dépôt absent.
2. Exécuter Konnaxion → Orgo → Konnaxion avec le shell Koali arrêté et les services propriétaires actifs. Capturer les deux côtés et les réponses avec la même transaction, puis lancer la campagne `e2e` en autonome.
3. Refaire le parcours avec Koali actif. Exporter le résumé du diagnostic spécialisé Koali et conserver les preuves métier de la nouvelle transaction. Vérifier les colonnes séparées de la matrice.
4. Confirmer le périmètre opérationnel du couloir historique EncyKlopedia → Daat → Kristal-Framework et obtenir les exports propriétaires si la baseline figée doit être exercée. Les deux frontières restent obligatoires dans le plan de ce profil et sans parcours actif dans la configuration fournie.
5. Rejouer les cas négatifs sur des copies des exports, notamment réponse absente, révision incompatible, empreinte modifiée et transactions disjointes. Contrôler les verdicts et l’absence de certification globale.
6. Ouvrir le `.pyw` sous Windows pour vérifier le logo, la lisibilité et la navigation. Importer le ZIP généré dans GitHub Audit v0.22.0 et vérifier la lecture ainsi que le maintien de la décision de gouvernance humaine.

## Vérifications exécutées le 11 novembre 2026

- 54 tests automatisés réussis avec les snapshots officiels IK et kOA Linux, dont les 38 tests existants. Les nouveaux cas couvrent notamment l’enveloppe IK valide et invalide, le reçu Linux, l’intégrité du journal, les tentatives disjointes, les modes mélangés et les révisions incompatibles.
- Campagne complète sur l’arborescence de référence reconstruite à partir des snapshots. 20 dépôts présents sur 53 dans l’inventaire, plus kOADiag lui-même hors inventaire. Les 13 niveaux ont rendu un verdict, sans erreur ni blocage. Verdict de campagne `PARTIAL`. 49 relations cartographiées et 61 entrées au registre. Les 11 sources documentaires, les 11 profils IK actifs et les 6 empreintes du verrou adopté sont conformes. Sur quatre frontières obligatoires, deux sont dans un parcours actif et aucune n’a de preuve runtime.
- Le 61e lien, Ekole → Akor, figure déjà comme `UNREVIEWED`. La documentation fournie situe Akor dans l’inventaire mais ne confirme pas une obligation de frontière. La décision reste ouverte.
- Une seconde campagne avec deux transactions synthétiques a corroboré les deux sauts du parcours Konnaxion–Orgo dans chacun des modes. L’export Audit contenait le résumé et 13 verdicts expurgés. Les chemins de travail, les URLs internes et les identifiants des transactions de test étaient absents. Le format historique de l’archive a été vérifié. Le programme importateur Audit v0.22.0 ne faisait pas partie des snapshots.
- Le `.pyw` a été compilé. La recette Windows, le rendu Tkinter et les échanges réels restent à valider sur le poste. La version livrée est la v5.4.0. La qualification v6.0 dépend de la recette et des preuves listées ci-dessus.
