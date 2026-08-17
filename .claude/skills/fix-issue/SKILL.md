---
name: fix-issue
description: Workflow complet pour fix d'une issue GitHub ha-maintenance-tracker — lecture issue, plan docs/plan/, implémentation, vérifications, commit. À utiliser quand l'utilisateur demande "fix issue #X" ou "résous l'issue #X".
---

# Fix Issue Workflow

Invoqué avec un numéro d'issue (ex: `/fix-issue 12`).

## Phase 1 — Lecture
1. `rtk gh issue view <num>` — titre, description, labels
2. Si l'issue référence des fichiers, des logs HA ou une PR, les lire
3. Identifier la branche cible : créer `fix/<num>-<slug>` ou `feat/<num>-<slug>` si nécessaire, sinon utiliser la branche en cours

## Phase 2 — Plan
Créer ou mettre à jour `docs/plan/Issue #<num> — <titre>.md` :

    # Issue #<num> — <titre>

    ## Contexte
    [Pourquoi, comportement observé vs attendu, version HA, lien GH]

    ## Fichiers impactés
    - [custom_components/maintenance_tracker/coordinator.py:120](custom_components/maintenance_tracker/coordinator.py#L120) — rôle
    - ...

    ## Étapes
    - [ ] Étape 1
    - [ ] Étape 2

    ## Vérification
    [Test ajouté, et comment reproduire dans une vraie instance HA]

Référencer les fichiers avec `path:line` (convention projet).

## Phase 3 — Implémentation

**Architecture — le coordinator est le seul écrivain.**
`MaintenanceCoordinator` détient et persiste l'état ; les entités lisent
`coordinator.data` et ne mutent jamais un compteur. Un nouveau comportement
passe par une méthode `async_*` du coordinator, qui met à jour, persiste et
rafraîchit en un seul endroit.

**Points de vigilance par type de changement :**

- **Nouvelle entité** → `translation_key` (la clé passée au constructeur de
  `MaintenanceEntity`) + entrée sous `entity.<platform>` dans `strings.json`.
  Une entité de tâche porte le placeholder `{task}` dans son nom.
- **Nouveau service** → `services.yaml` + section `services` de `strings.json` +
  méthode sur l'entité ciblée. **Et** un garde par défaut dans
  `MaintenanceEntity`, sinon cibler une autre entité de la même plateforme
  lève une `AttributeError` au lieu d'un message clair.
- **Nouveau champ persistant** → `from_dict` **et** `as_dict` dans `models.py`,
  avec une valeur par défaut tolérante aux données déjà stockées. Si le format
  change de façon incompatible, bumper `STORAGE_VERSION` et écrire la migration.
- **Détection de cycle** → toute modification de la machine à états doit être
  couverte par un test dans `tests/test_coordinator.py` (cycle complet, burst
  court rejeté, pause qui ne coupe pas le cycle, source `unavailable`).
- **Carte Lovelace** → JS natif, aucun build. Éditer directement
  `custom_components/maintenance_tracker/frontend/maintenance-tracker-card.js`.

**i18n obligatoire** : toute string visible passe par `strings.json`, puis
`python scripts/build_translations.py` pour régénérer `translations/en.json`.
`translations/fr.json` est écrit à la main — le mettre à jour dans le même
commit, sans quoi l'interface repasse en anglais pour les utilisateurs FR.

**Ne jamais** casser la compatibilité des données persistées d'un utilisateur :
les compteurs sont un historique de vie, pas un cache.

## Phase 4 — Vérifications

Toutes doivent passer avant de commiter (ce sont exactement les checks de la CI) :

```bash
rtk ruff check .
rtk ruff format --check .
rtk python scripts/build_translations.py --check
rtk pytest
rtk node --check custom_components/maintenance_tracker/frontend/maintenance-tracker-card.js
```

Un fix sans test de non-régression n'est pas terminé.

## Phase 5 — Commit
Format :
- `fix(#<num>): <description>` pour bugfix
- `feat(#<num>): <description>` pour feature
- `chore(#<num>): <description>` pour cleanup
Plusieurs commits autorisés si phases distinctes.

**Ne pas** bumper la version dans `manifest.json` ici (c'est le rôle de
`/ready-to-merge` avant fusion sur `main`).
**Ne pas** push automatiquement — attendre validation utilisateur.

## Rappels conventions projet
- Préfixer toutes les commandes par `rtk`
- Réponses en français ; code, commentaires et docstrings en anglais
  (le dépôt est public et destiné à la communauté HA)
- Home Assistant minimum : **2025.12** — ne pas utiliser d'API plus récente
  sans remonter `hacs.json` et le README
- Le dépôt de référence pour les API HA est `/var/www/home-assistant-core` :
  le lire plutôt que de deviner une signature
