# kOADiag 5.7.0 — Interaction Kernel et sécurité E2E

## Deux parcours non destructifs

**Validation rapide totale** : sonde les 21 allocations C0 et les connexions déclarées ; ni Docker, ni données métier, ni transactions E2E.

**Validation approfondie** : ajoute santé HTTP, campagne LevelUpDiag et inventaire des suites de test propriétaires (mais **n'exécute pas** ces suites). Les rapports de niveau donnent maintenant un plan de correction documenté : collectes incomplètes, désaccord documentaire, inventaires, sources de preuves IK.

## E2E transactionnel distinct dans le Centre

Dans **Centre de validation → Interaction Kernel E2E** :

1. Indiquer la **clé exacte d'un World de TEST Konnaxion** disposant d'une Release active.
2. Vérifier réellement que les deux bases sont isolées, sans donnée de production ni donnée personnelle. Les simples noms de bases ou drapeaux `.env` ne constituent **pas** une preuve technique d'isolement.
3. Cliquer **ATTESTER BASES TEST**, puis confirmer avec la phrase demandée. Cette attestation locale expire après une heure ; elle ne contient aucun secret.
4. Cliquer **PRÉCONTRÔLE IK** : registre C0, services HTTP, variables privées requises (présence seulement), routes IK Docker et services Docker. Un lancement Django natif par Uvicorn ne remplace pas le conteneur Django nécessaire au script officiel.
5. Seulement si le précontrôle passe et si tu acceptes des écritures dans les bases isolées, cliquer **EXÉCUTER LE E2E OFFICIEL**. Une nouvelle confirmation explicite est obligatoire à chaque tentative.

Le test utilise **uniquement le script maintenu dans le dépôt Orgo** :
`C:\mycode\Orgo\Orgo\validation\konnaxion-orgo-ik\run-e2e.ps1`

Il lui passe explicitement `-OrgoHostUrl http://127.0.0.1:21111`, le `-WorldKey`, et `-ExportObservations`. Le script exécute les scénarios métier qu'il sait valider, notamment émission, réception, idempotence et retour d'impact. **kOADiag ne réimplémente pas ces règles métier.**

### Pile Docker et fichier dotenv

- Prépare Orgo dans le projet **`orgo-ik-test`**, avec l’API sur `127.0.0.1:21111` et l’API et le worker branchés sur `host.docker.internal:5432/orgo_test`. Le précontrôle reconnaît `orgo-ik-test-api-1`, `orgo-ik-test-worker-1` et `orgo-test-postgres`.
- Prépare Konnaxion dans le projet **`backend`** avec `docker-compose.local.yml`, `docker-compose.e2e-db.local.yml` et `docker-compose.worlds.local.yml`. Django et Celery doivent utiliser `kx-e2e-postgres/konnaxion_e2e`; Django publie `127.0.0.1:21131`. Le précontrôle exécute le filtre d’URL installé dans le conteneur Celery pour vérifier que l’URL C0 est acceptée.
- Le jeton machine reste dans **`C:\mycode\Konnaxion\Konnaxion\backend\.envs\.local\.django`**, hors de Git. Le kit et Docker lisent ce même fichier. Il contient `IK_ORGO_TOKEN`, `IK_ORGO_TARGET_ORGANIZATION`, `IK_ORGO_ALLOWED_ORGANIZATION`, `IK_ORGO_INBOUND_TOKEN` et `IK_ORGO_INTERACTIONS_URL`. Le précontrôle compare le jeton et la cible chargés dans Django/Celery, vérifie à Orgo le périmètre du jeton machine, et contrôle le jeton de retour et l’organisation autorisée côté Django.
- L’API Orgo doit utiliser `konnaxion_decision_v1` et un label de décision. Le worker doit cibler `http://host.docker.internal:21131/api/integrations/ik/konnaxion/interactions/` et son `KONNAXION_IK_TOKEN` doit correspondre au jeton entrant de Django.
- Le précontrôle inspecte les conteneurs et sonde les deux API. L’attestation reste requise pour l’isolement des données. Il ne crée aucun jeton et ne lance ni Docker ni aucune transaction. Si le jeton expire, renouvelle-le dans le fichier dotenv puis recharge la pile E2E avant de reprendre.
- N14 utilise la pile isolée préparée. L’ancien démarrage automatique `--start-test-stack` est bloqué dans N14 car il ciblerait le Compose Orgo standard. Depuis cette version, utilise **Centre de validation → Interaction Kernel E2E** pour tester la pile préparée.

### Autorisation temporaire

Le bouton d'attestation crée `ik-e2e-test-authorization.local.json` dans le dossier kOADiag. **Ne pas l'ajouter à Git.** Il contient uniquement le World autorisé, la date d'expiration et ta déclaration d'isolement. Tu peux supprimer le fichier à tout moment pour révoquer cette déclaration. **Cette attestation ne démontre pas l'isolement réel** : il faut le vérifier à la source dans les deux bases et leurs volumes.

Le lanceur rejette le fichier absent, expiré, mal formé ou qui ne mentionne pas le World choisi. Le démarrage E2E exige aussi une confirmation indépendante dans l'interface ; **aucun mode automatique**, même « approfondi », ne peut le déclencher.

### Résultat et preuves

Rapports structurés et expurgés dans :
`reports\Diagnostic-kOA-Digital-Ecosystem\ik-e2e\*.json`

Sont conservés le verdict, le code de retour pour une exécution kOADiag, l’empreinte du script exécuté, le marqueur PASS et, si le kit les fournit, les statuts, les six horodatages UTC et l’empreinte de corrélation. Les secrets et la sortie brute ne sont pas conservés.

**Importer une sortie** accepte un fichier UTF-8 d’une exécution PowerShell comprenant la ligne avec le World et sa release, `KOA_OBSERVATIONS=` et le marqueur exact `KONNAXION <-> ORGO IK E2E PASS`. L’entrée apparaît dans **Dernier résultat** avec la provenance `terminal_import`, sans relancer le test.

Un **PASS du kit officiel ne certifie pas toutes les frontières de l'écosystème**, ni les modes autonome/intégré. Les preuves doivent encore être rapprochées des traces indépendantes de chaque dépôt avec révision, horodatage et corrélation.

## Ce que cette version ne réalise pas automatiquement

Elle ne modifie pas les dépôts Orgo/Konnaxion, leurs configurations `.env`, les migrations, les volumes Docker, les secrets, les décisions humaines du registre, les empreintes documentaires ou les limites globales de collecte. Elle ne lance pas non plus toutes les suites de tests applicatifs de dépôts hétérogènes : elle les **référence** en lecture seule. Une exécution sûre de chacune nécessitera un contrat de test propre à son dépôt, avec environnement et effets documentés.
