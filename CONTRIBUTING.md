# Contributing

This repository is a personal fork used to test changes before submitting
pull requests (PRs) to the upstream/main FanFicFare repository. Use this
fork as a staging area for development and local testing.

Branching & PR workflow (preferred)

- Work on a topic branch in this fork. Example:

  ```sh
  git checkout -b tmp-work
  # make commits as you develop
  ```

- When ready to submit a clean PR to upstream, squash your work into a single
  commit and publish a new branch that contains only that commit.

- Two simple ways to produce the single-commit branch:

  1) Create a single commit using `reset --soft` (non-interactive):

     - Bash / POSIX shells:

       ```sh
       git reset --soft $(git merge-base main tmp-work)
       git commit -m "Short, descriptive commit message"
       git checkout -b single-commit-branch
       git push origin single-commit-branch
       ```

     - PowerShell (works in this repo's Windows environment):

       ```powershell
       git reset --soft (git merge-base main tmp-work)
       git commit -m "Short, descriptive commit message"
       git checkout -b single-commit-branch
       git push origin single-commit-branch
       ```

  2) Interactive rebase against `main` and squash (manual but familiar):

     ```sh
     git rebase -i main
     # squash commits to make one commit, then
     git checkout -b single-commit-branch
     git push origin single-commit-branch
     ```

- Open the PR from `single-commit-branch` to the upstream `main` branch.
  - In the PR description include: what you changed, how you tested, and
    any manual verification steps (build, run, or plugin packaging).

Example local sequence

```sh
git checkout -b tmp-work
# work and commit as needed
# produce single-commit-branch (see methods above)
git push origin single-commit-branch
# open PR from single-commit-branch -> upstream main
```

Pre-PR checklist

- Run tests locally:

  ```sh
  pytest -q tests/
  ```

- Smoke-check CLI:

  ```sh
  python -m fanficfare.cli --help
  ```

- Build the Calibre plugin (if you modified plugin or vendored deps):

  ```sh
  python makeplugin.py
  # Inspect FanFicFare.zip for expected contents
  ```

- If you added or modified adapters:
  - Add/update tests under `tests/` using existing fixture patterns
    (`tests/fixtures_*.py`).
  - Ensure adapter module is imported in `fanficfare/adapters/__init__.py`
    so it will be auto-registered.

PR Content Guidance

- Keep PRs focused and small where possible.
- Include one-line summary in the commit message and a short body explaining
  why the change was made and how it was tested.

Want more?

If you want, I can add a short `CONTRIBUTING.md` checklist to the `.github/`
folder, include a ready-made adapter template, or produce a small CI recipe
for running `pytest` on GitHub Actions. Tell me which you'd prefer.
