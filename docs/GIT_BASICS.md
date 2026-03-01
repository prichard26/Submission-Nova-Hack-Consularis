# Git basics

## Branches

```bash
git branch                    # list branches
git checkout -b my-feature    # create + switch to branch
git checkout main             # switch to main
git branch -d my-feature      # delete branch (after merge)
```

---

## Pull

```bash
git checkout main
git pull
```

Or for a specific branch: `git pull origin main`

---

## Push

```bash
git add .
git commit -m "message"
git push
```

First time for a new branch: `git push -u origin my-feature`

---

## Team flow (same repo, different features)

```bash
# 1. Start from latest
git checkout main
git pull

# 2. Create your feature branch
git checkout -b my-feature

# 3. Work and push
git add .
git commit -m "message"
git push -u origin my-feature

# 4. When main has new commits — update your branch
git checkout main
git pull
git checkout my-feature
git merge main
git push

# 5. When feature is merged (e.g. via PR) — clean up
git checkout main
git pull
git branch -d my-feature
```
