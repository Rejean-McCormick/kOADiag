# Preuves passives requises pour Konnaxion ↔ Orgo

Ce fichier définit un **contrat de métadonnées d'export** pour les diagnostics
spécialisés. Il ne crée aucune trace et ne lance aucun appel applicatif.

## Parcours officiel actif

- `journey_id`: `konnaxion-orgo-decision-impact`
- Saut 1 : `Konnaxion` → `Orgo`, `contract=governance.decision.execute/1.0.0`
- Saut 2 : `Orgo` → `Konnaxion`, `contract=accountability.impact.publish/1.0.0`
- Les deux sauts doivent partager un même `correlation_id` réel.
- Chaque saut doit avoir une émission, une réception, une réponse/reçu validé,
  des dates UTC cohérentes et une provenance indépendante.

## Champs dans les exports JSON, JSONL ou NDJSON

| Champ | Règle |
|---|---|
| `correlation_id` | Identifiant opaque identique sur tous les sauts; le rapport conserve un hash |
| `journey_id` | Nom exact du parcours actif |
| `source_repo`, `target_repo` | Noms de dépôts canoniques du saut |
| `contract` | Nom/version exacts du profil IK; obligatoire pour la preuve spécifique du profil |
| `phase` | `sent`, `received`, `response` (ou `published`, `consumed` si événement sans réponse) |
| `timestamp` | ISO 8601 avec fuseau, du vrai événement |
| `status` | Réponse réellement observée et réussie pour `response` |
| `method`, `path` | Si échange HTTP; sinon omettre |

Les exports **doivent être créés par les outils dédiés et portés par leurs
propriétaires respectifs**. Pour chaque saut, configurer deux descripteurs
`exchange_trace_files` avec des `owner_repo` explicites, chacun pointant sur
un fichier situé sous `C:\mycode`. Un reçu peut figurer dans l'export du
récepteur. Le parseur accepte les alias `contract_id`, `ik_profile`, `profile`.

Le fichier local `koa-ecosystem-diag.config.local.json` est le bon endroit
pour ces descripteurs. Ajouter seulement des chemins réellement existants et
inspectés. Ne pas fournir d'identifiant de transaction fictif pour obtenir
un statut PASS.

Le validateur exigera :
- deux sources indépendantes avec empreintes distinctes et propriétaire exact ;
- émission/réception cohérentes par contrat, identité et saut ;
- réponse/reçu attribué au récepteur lorsque demandé ;
- horodatages cohérents, frais (politique actuelle : 168 h) ;
- même transaction pour les deux sauts, dans l'ordre.

Un simple GET `/health`, un contrat présent dans `/docs` ou un rapport
`PASS` d'un diagnostic interne n'est pas une preuve E2E suffisante.

## Précaution de sécurité

Ne pas mettre dans les exports : payload métier, secrets, tokens, cookies,
identifiants personnels ou URLs privées. Préserver les journaux originaux
hors du dossier public et ne partager que les métadonnées nécessaires.
