# kOADiag C0 v5.5.4 — Vérification de disponibilité après démarrage

## Problème corrigé

Le 19 novembre 2026, la commande « Redémarrer » a lancé kOA et Konnaxion vers 21:39:06 ; l'audit automatique a démarré vers 21:39:09 alors que les serveurs Next.js prenaient **4,4 et 5,3 secondes** pour être prêts. Le superviseur v5.5.3 renvoyait code 0 immédiatement après la création des processus, sans attendre les ports.

## Nouvelle logique

- Après le lancement d'un groupe automatisable, attendre l'ouverture de **tous ses ports** C0, avec deux sondes TCP positives successives.
- Afficher « TCP READY » port par port, puis « DISPONIBILITÉ TCP CONFIRMÉE ».
- Délai maximal **75 secondes par groupe** (15 secondes pour une instance déjà suivie).
- Si les ports restent indisponibles, renvoyer un code d'erreur non nul et conserver les journaux. Ne pas annoncer la réussite.
- kOADiag ne lance son audit global qu'après la fin de ces vérifications.
- Pour Orgo, redémarrage Compose inchangé ; désormais ses ports exposés sont vérifiés aussi.
- Cela vérifie **l'accessibilité TCP**, pas l'identité certifiée, l'authentification ou une transaction Interaction Kernel de bout en bout.

## Installation Windows

1. **Fermer kOADiag**.
2. Décompresser le ZIP dans un dossier à part.
3. Lancer `INSTALLER-C0-READY.bat` ; le chemin est auto-détecté : `C:\mycode\kOA_Digital_Ecosystem\kOADiag`.
4. Lancer `VERIFIER-C0-READY.bat` : attendu « conformes 5/5 » (le guide présent dans le dépôt compte comme fichier ajouté).
5. Rouvrir kOADiag, onglet « Ports C0 », choisir « Essentiels » puis « Redémarrer », après consultation du plan et confirmation.
6. Dans le journal, vérifier les lignes `TCP READY` et `DISPONIBILITÉ TCP CONFIRMÉE` avant l'audit automatisé.

Restauration : `ANNULER-C0-READY.bat`. Sauvegardes séparées de la vague 5.5.3.

## Limites

- Les processus non supervisés ne sont jamais arrêtés.
- Aucun service Windows n'a été testé en direct depuis la session de création du correctif.
- Pour confirmer le fonctionnement réel : consulter le nouveau rapport `ports-c0.json`, plus les tests IK authentifiés.
