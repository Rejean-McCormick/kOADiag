# kOADiag 5.5.3 — contrôle local des services C0

Le panneau **Ports C0** propose maintenant :

1. **Tester tous les ports C0** : lecture seule, sonde les 21 ports déclarés dans le registre C0.
2. **Essentiels** (Orgo, Konnaxion et kOA) ou **Tous les groupes** (les dix groupes du plan, couvrant 21 ports).
3. Choisir **Démarrer**, **Redémarrer** ou **Arrêter supervisés**, puis **Voir le plan**.
4. Une fenêtre présente la liste réelle des groupes, leur caractère automatisable ou manuel, et les effets possibles. **La case de confirmation est obligatoire** avant une action.
5. L'action s'exécute dans un processus enfant Windows; l'interface reste utilisable et le **Journal d'exécution** reçoit les messages. Un rapport texte est conservé sous `reports/Diagnostic-kOA-Digital-Ecosystem/reboot-c0/`.
6. Après chaque action, kOADiag exécute un **nouveau contrôle de l'ensemble des ports C0**; les rapports de sondes restent dans `reports/Diagnostic-kOA-Digital-Ecosystem/ports-c0/`.

## Protection des applications et des données

- Le registre central `C:\mycode\kOA_Digital_Ecosystem\kOA_Digital_Ecosystem\config\local-dev-ports.v1.json` est la **seule source de vérité**. Le plan est refusé si ses 21 services ne correspondent plus au registre ou si des ports sont en doublon.
- **Aucun `taskkill` par port**. Pour les processus Python/Node lancés par le superviseur, les PID et leur date de création sont vérifiés avant l'arrêt. Les processus démarrés par d'autres outils ne sont pas arrêtés automatiquement, même si leur port est occupé.
- L'option graphique n'utilise **jamais** `--force-owned`.
- Le groupe Orgo utilise **Docker Compose du dépôt Orgo uniquement**. `restart` / `up -d` ne supprime ni bases ni volumes ; **Arrêter supervisés** ne stoppe pas ce groupe Docker.
- Ne touche jamais aux fichiers `.env`, aux secrets, aux données, aux services distants ou aux applications en production.
- Les **9 ports non automatisés** (Koali intégré, Capsule Agent/Manager, Ékole OpsConsole) nécessitent toujours leurs lanceurs propriétaires. Ils sont explicitement indiqués **MANUEL**, pas considérés comme redémarrés.
- Les prérequis doivent déjà être présents : Node, npm/pnpm, Docker Desktop, Python et les environnements virtuels des dépôts.
- Un port accessible n'est pas une preuve de connexion authentifiée ni de transaction Interaction Kernel de bout en bout.

## Cas pratiques

**Après installation des migrations de ports** : exécuter une première sonde, puis `Essentiels` + `Démarrer`. Si les services sont déjà actifs et externes au superviseur, la vérification des ports les montrera ouverts, mais kOADiag n'arrêtera pas leurs processus.

**Redémarrage général** : sélectionner `Tous les groupes` + `Redémarrer`, examiner les groupes manuels, cocher l'autorisation puis confirmer. Les erreurs de prérequis et les refus apparaissent dans le journal et dans la nouvelle sonde.

**Restitution** : envoyer les rapports `ports-c0/*.json` et `reboot-c0/*/reboot-c0.txt` après l'opération. Ces rapports ne doivent pas contenir de secrets, mais il reste conseillé de les relire avant partage.

**Important** : le kit a été testé sur une copie de l'application et un registre C0 fictif. Il ne redémarre pas Windows et ne prétend pas que les services de ton PC ont été réellement démarrés depuis ChatGPT.
