# Contributing to AURUMTRACE

This document describes how the team (Saiesha, Utkarsh, Niharika) works together on this repository during the initial development phase.

## Branch model (initial development phase)

| Branch | Role | Who writes to it |
| --- | --- | --- |
| `feat/landing-page` | **Shared development base.** Default branch on GitHub. Everything integrates here. | Pull requests only — no direct pushes |
| `<type>/<topic>` | Your personal working branch, created from `feat/landing-page` | Only its owner |
| `main` | Reserved for the first stable release. **Currently empty — do not push to it.** | Nobody, until the release step below |

Rules:

- Never push directly to `feat/landing-page` or `main`. All changes go through a pull request.
- Never force-push a branch someone else has pulled, and never rewrite shared history.
- One topic per branch, one branch per person. Don't commit to someone else's branch without asking.

## Branch naming

```
<type>/<short-kebab-case-topic>
```

| Type | Use for | Example |
| --- | --- | --- |
| `feat/` | New feature or section | `feat/pricing-section` |
| `fix/` | Bug fix | `fix/nav-overlap-mobile` |
| `perf/` | Performance work | `perf/hero-particle-budget` |
| `refactor/` | Restructuring without behaviour change | `refactor/scene-clock` |
| `style/` | Visual/CSS-only polish | `style/journey-card-spacing` |
| `docs/` | Documentation | `docs/setup-guide` |
| `chore/` | Tooling, dependencies, config | `chore/eslint-setup` |

Keep names lowercase, hyphen-separated and under ~40 characters. Name the change, not the person.

## Commit messages

Use a short imperative subject (≤ 72 chars), optionally prefixed with the type:

```
feat: add pricing section with plan comparison
fix: stop node labels sliding under the nav
```

Add a body when the *why* isn't obvious.

## Getting started (Utkarsh and Niharika)

One-time setup:

```bash
git clone https://github.com/Saiesha1103/Auramtrace.git
cd Auramtrace
git checkout feat/landing-page
npm ci
npm run dev
```

`feat/landing-page` is the default branch, so a fresh clone is already on it — the `checkout` just makes sure.

### Start a piece of work

Always branch from the latest shared base:

```bash
git checkout feat/landing-page
git pull
git checkout -b feat/your-topic
```

### Save and share your work

```bash
git add <files>
git commit -m "feat: describe the change"
git push -u origin feat/your-topic   # first push; afterwards just `git push`
```

### Open a pull request

1. On GitHub, open a PR from your branch.
2. **Check that the base branch is `feat/landing-page`** (not `main`).
3. Fill in the PR template, add screenshots or a short recording for visual changes.
4. Request a review from one of the other two team members.

### Keep your branch up to date

When `feat/landing-page` moves on while you're working, merge it into your branch (no rebasing of pushed branches, so nobody ever needs to force-push):

```bash
git fetch origin
git merge origin/feat/landing-page
# resolve any conflicts, then:
npm run build
git push
```

## Merge workflow

A PR into `feat/landing-page` can be merged when:

- [ ] At least **one approval** from another team member
- [ ] `npm run build` passes (typecheck + production build)
- [ ] Checked in the browser at desktop and mobile widths (no horizontal scroll)
- [ ] `prefers-reduced-motion` still works if motion was touched
- [ ] Demo data stays clearly labelled as illustrative
- [ ] Branch is up to date with `feat/landing-page`

Merge with **"Squash and merge"** so each PR lands as one clean commit on the base. The PR author merges after approval, then deletes their branch on GitHub (the button appears after merging). Locally:

```bash
git checkout feat/landing-page
git pull
git branch -d feat/your-topic
```

## Files that must stay local

Never commit:

- `.claude/` — local Claude Code preview config (e.g. `.claude/launch.json`)
- `node_modules/`, `dist/`, `*.local`, `.env*`

If you have a machine-specific file that git keeps showing, ignore it **locally** without touching the shared `.gitignore`:

```bash
echo ".claude/" >> .git/info/exclude
```

## Moving to `main` (later, needs team agreement)

When the initial development work is complete, the repo owner will:

1. Create `main` from the final `feat/landing-page` commit.
2. Switch the GitHub default branch to `main` and add branch protection (PR + review required).
3. From then on, feature branches are created from and merged into `main`.

Until that is agreed and announced, keep targeting `feat/landing-page`.
