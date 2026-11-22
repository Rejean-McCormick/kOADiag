# kOADiag — contrôle de tous les ports C0

Le diagnostic lit **le registre central en vigueur** :

`C:\mycode\kOA_Digital_Ecosystem\kOA_Digital_Ecosystem\config\local-dev-ports.v1.json`

Aucune duplication des numéros de ports dans ce module. Le registre de la vague 2
contient 21 services ; si C0 est enrichi, ce contrôle suit les nouvelles entrées.

## Utilisation

- Interface graphique : ouvrir `Lancer-Diagnostic-kOA-Digital-Ecosystem.cmd`, onglet **Ports C0**, puis **TESTER TOUS LES PORTS C0**.
- Windows, en double-clic : `TESTER-PORTS-C0.bat`.
- Terminal : `py -3 Diagnostic-kOA-Digital-Ecosystem-CLI.py ports --root C:\mycode`.
- Répertoire personnalisé : ajouter `--registry <chemin-registre-v1.json>` et, au besoin, `--port-out-dir <dossier>`.

Les résultats de chaque exécution sont enregistrés en **CSV**, **JSON** et **TXT** dans :

`reports/Diagnostic-kOA-Digital-Ecosystem/ports-c0/<horodatage>/`

### Lecture des résultats

- `STOPPED` : aucun processus ne répond sur ce port ; peut être normal si le service n'est pas démarré.
- `TCP_OPEN_UNVERIFIED` : le port accepte TCP, mais le protocole ou l'identité n'est pas établi.
- `HTTP_UNVERIFIED` : le serveur répond HTTP, mais aucun marqueur d'identité fiable.
- `FAMILY_MATCH` : le titre HTTP correspond à la famille de produit, pas forcément à l'instance voulue.
- `IDENTITY_CONFIRMED` : le service annonce l'en-tête optionnel `X-KOA-Service-Id` égal à son ID de registre.
- `WRONG_SERVICE` : titre HTTP d'un autre système, ou en-tête d'identité explicite différent.
- `SCAN_ERROR` : la sonde n'a pas pu être exécutée correctement.

Il n'est **pas nécessaire de démarrer les 21 services** pour utiliser le contrôle : les services volontaires à l'arrêt seront recensés sans invention de collision.

### Interaction Kernel

Le rapport inclut des **paires d'endpoints** Orgo/Konnaxion, Koali/Konnaxion, Orgo Worlds et kOA.
Leur état signifie seulement que les ports correspondants sont accessibles **depuis Windows**.
Il ne prouve ni la communication de conteneur à conteneur, ni l'authentification, ni l'exécution d'un vrai workflow IK.
Pour l'IK, conserver une validation E2E native distincte avec des preuves métier.

### Sécurité et précautions

- Lecture seule : aucune commande de démarrage, arrêt, réservation ou reconfiguration.
- Connexions **uniquement à 127.0.0.1**, TCP et HTTP `GET /`, pas de suivi de redirections.
- Le corps HTTP n'est pas conservé ; pas d'envoi de jetons ni de secrets.
- Aucun changement des ports internes Docker, des agents distants et des ports de production.
- Si le registre manque ou comporte un doublon, arrêt explicite sans ports inventés.
- Le `.env` et les configurations privées de chaque projet ne sont pas modifiés.

### Codes de retour CLI

- `0` : toutes les identités sont confirmées au moins au niveau du produit.
- `10` : un ou plusieurs ports arrêtés ou non vérifiés, **pas automatiquement un bug**.
- `20` : mauvais service ou erreur de sonde ; enquête nécessaire.
- `30` : erreur de chargement ou de validation du registre via l'entrée CLI.

Le contrôle des ports est indépendant des niveaux N00–N14 de la campagne générale.
Les anciennes captures et preuves historiques ne sont pas réécrites.
