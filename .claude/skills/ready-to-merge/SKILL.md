---
name: ready-to-merge
description: Check pré-merge sur main pour ha-maintenance-tracker — vérifie le bump de version (manifest.json + carte JS), rejoue les checks CI, propose le bump si manquant et rappelle la release HACS. À invoquer avant tout merge/PR vers main.
---

# Pré-merge sur main

Workflow à exécuter avant `git merge`, `gh pr merge` ou `git push origin main`.

## Phase 1 — État de la branche
1. `rtk git rev-parse --abbrev-ref HEAD` — branche courante (refuser si déjà sur `main`)
2. `rtk git fetch origin main`
3. `rtk git log --oneline origin/main..HEAD` — commits qui vont être mergés
4. `rtk git diff --stat origin/main..HEAD` — ampleur des changements

## Phase 2 — Vérification bump version

La version vit à **deux endroits qui doivent rester identiques** :
- `custom_components/maintenance_tracker/manifest.json` → `version` (lue par HACS)
- `custom_components/maintenance_tracker/frontend/maintenance-tracker-card.js`
  → `const VERSION` (sert le cache-busting du navigateur et le log console)

1. Lire les deux valeurs locales — **si elles divergent, c'est un bug à corriger
   avant tout**
2. `rtk git show origin/main:custom_components/maintenance_tracker/manifest.json` — version sur main
3. Comparer :
   - Si version locale > version main → ✅ bump déjà fait
   - Si version locale == version main → ⚠️ bump manquant, passer à Phase 3

Vérifier aussi, si les commits touchent aux API Home Assistant utilisées :
`hacs.json` → `homeassistant` (version minimale) et la ligne correspondante du README.

## Phase 3 — Bump si manquant
Analyser les commits `origin/main..HEAD` pour suggérer le type de bump :
- `feat(...)` présent → **minor** (0.1.X → 0.2.0)
- `fix(...)` ou `chore(...)` seuls → **patch** (0.1.X → 0.1.X+1)
- Changement cassant la config existante ou le format de stockage → **major**,
  à demander explicitement

Proposer la nouvelle valeur, attendre validation, puis :
1. Éditer `version` dans `manifest.json`
2. Éditer `VERSION` dans `maintenance-tracker-card.js` (même valeur)
3. `rtk git add custom_components/maintenance_tracker/manifest.json custom_components/maintenance_tracker/frontend/maintenance-tracker-card.js`
4. `rtk git commit -m "chore: bump version to <X.Y.Z>"`

## Phase 4 — Rejouer les checks CI en local

```bash
rtk ruff check .
rtk ruff format --check .
rtk python scripts/build_translations.py --check
rtk pytest
rtk node --check custom_components/maintenance_tracker/frontend/maintenance-tracker-card.js
```

`hassfest` et la validation HACS ne tournent qu'en CI : si une PR est ouverte,
vérifier `rtk gh pr checks <num>` avant de conclure.

## Phase 5 — Récap final
Afficher :
- Branche source → cible (`main`)
- Nombre de commits, fichiers modifiés
- Nouvelle version
- Plan(s) `docs/plan/` concerné(s) : sont-ils marqués ✅ complets ?
- Si des entités, services ou options de carte ont changé : le README est-il à jour ?
- Commande de merge suggérée selon le contexte :
  - PR ouverte → `rtk gh pr merge <num> --squash`
  - Pas de PR → `rtk git checkout main && rtk git merge --no-ff <branche>`

## Phase 6 — Rappel release HACS

HACS sert les mises à jour depuis les **releases GitHub**, pas depuis `main`.
Un merge seul ne livre rien aux utilisateurs. Après le merge, rappeler :

```bash
rtk gh release create v<X.Y.Z> --title "v<X.Y.Z>" --generate-notes
```

Le tag doit correspondre exactement à la `version` du `manifest.json`.

**Ne pas exécuter le merge ni la release automatiquement** — laisser
l'utilisateur décider.
