# Fresh GitHub repo (MaxxWasHere/blossom)

The stable source and releases live at **https://github.com/MaxxWasHere/blossom** (lowercase). Beta is unchanged: **https://github.com/MaxxWasHere/blossombeta**.

Local `main` was rebuilt as a **single squashed commit** (author `MaxxWasHere` only) so the new repo has no old contributor noise. `.cursor/`, `discord-bot/`, secrets, and build artifacts stay gitignored.

## Before you push

1. On GitHub: delete the old `MaxxWasHere/Blossom` repo if you still have it (or leave it archived).
2. Ensure **https://github.com/MaxxWasHere/blossom** exists (empty or LICENSE-only is fine).
3. Confirm remote: `git remote -v` → `origin` → `https://github.com/MaxxWasHere/blossom.git`

## First push (empty or LICENSE-only remote)

From the repo root, on branch `main`:

```powershell
git push -u origin main --force
```

Use `--force` because history was replaced with one initial commit. Safe only on a fresh or intentionally reset remote.

If GitHub asks for auth, sign in with your account or a PAT with `repo` scope. **Do not** push if auth fails — fix credentials first, then run the same command again.

## After push

- **Releases:** Re-create stable releases on `blossom` (upload `Blossom-{version}.exe`). Old `Blossom` release URLs will 404; the in-app updater now points at `MaxxWasHere/blossom`.
- **Beta:** No repo rename — keep shipping pre-releases on `blossombeta` as before.
- **Clone URL:** `git clone https://github.com/MaxxWasHere/blossom.git`

## Verify locally

```powershell
git log -1 --format="%H %an <%ae> %s"
git remote get-url origin
```

Expected: one commit titled `Initial Blossom macro release`, author `MaxxWasHere`, remote ending in `blossom.git`.
