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

### Préconditions supplémentaires

- Orgo Web/API et Konnaxion Web/API doivent répondre sur leurs ports C0. Les API sont vérifiées sur les routes de santé déclarées.
- Pour le test propriétaire, la pile Konnaxion **Docker** doit tourner (`django`, `redis`, `celeryworker`) et les services Orgo (`postgres`, `api`, `worker`). Le précontrôle ne démarre ni ne recrée les conteneurs.
- Variables privées requises : Orgo `POSTGRES_PASSWORD`, `KONNAXION_IK_URL`, Konnaxion `IK_ORGO_TOKEN`, `IK_ORGO_TARGET_ORGANIZATION`, `IK_ORGO_INTERACTIONS_URL`. Seule leur **présence** et la conformité des **routes IK locales** sont affichées. Les valeurs secrètes ne sont jamais incluses dans les rapports.
- Les routes inter-conteneurs doivent être configurées sur `host.docker.internal:21131` (Orgo vers Konnaxion) et `host.docker.internal:21111` (Konnaxion vers Orgo), dans l'environnement Docker pris en charge. Un service exposé sur l'interface loopback hôte peut rester inaccessible depuis un conteneur : le précontrôle local ne peut pas certifier l'acheminement Docker de bout en bout.
- PowerShell 7.5+ et Docker CLI sont requis. Le script propriétaire vérifie lui-même la version PowerShell.

### Autorisation temporaire

Le bouton d'attestation crée `ik-e2e-test-authorization.local.json` dans le dossier kOADiag. **Ne pas l'ajouter à Git.** Il contient uniquement le World autorisé, la date d'expiration et ta déclaration d'isolement. Tu peux supprimer le fichier à tout moment pour révoquer cette déclaration. **Cette attestation ne démontre pas l'isolement réel** : il faut le vérifier à la source dans les deux bases et leurs volumes.

Le lanceur rejette le fichier absent, expiré, mal formé ou qui ne mentionne pas le World choisi. Le démarrage E2E exige aussi une confirmation indépendante dans l'interface ; **aucun mode automatique**, même « approfondi », ne peut le déclencher.

### Résultat et preuves

Rapports structurés et expurgés dans :
`reports\Diagnostic-kOA-Digital-Ecosystem\ik-e2e\*.json`

Sont conservés : statut, code de retour, empreinte du script officiel, présence du marqueur PASS et, lorsque le script fournit `KOA_OBSERVATIONS`, une empreinte de l'observation et des identifiants hachés. **Ni stdout/stderr brut, ni token, ni mot de passe** ne sont exportés par kOADiag.

Un **PASS du kit officiel ne certifie pas toutes les frontières de l'écosystème**, ni les modes autonome/intégré. Les preuves doivent encore être rapprochées des traces indépendantes de chaque dépôt avec révision, horodatage et corrélation.

## Ce que cette version ne réalise pas automatiquement

Elle ne modifie pas les dépôts Orgo/Konnaxion, leurs configurations `.env`, les migrations, les volumes Docker, les secrets, les décisions humaines du registre, les empreintes documentaires ou les limites globales de collecte. Elle ne lance pas non plus toutes les suites de tests applicatifs de dépôts hétérogènes : elle les **référence** en lecture seule. Une exécution sûre de chacune nécessitera un contrat de test propre à son dépôt, avec environnement et effets documentés.
