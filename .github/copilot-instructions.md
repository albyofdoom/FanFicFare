# Copilot / AI agent instructions for FanFicFare

This file gives concise, actionable guidance for AI coding agents working in this repository.

Overview
- The project has two primary runtimes:
  - The library/CLI: the `fanficfare/` package. Entry point: `fanficfare.cli:main` (`python -m fanficfare.cli`).
  - The Calibre plugin: code under `calibre-plugin/` (main integration in `calibre-plugin/fff_plugin.py`).

Key directories & files
- `fanficfare/` — core library: `adapters/`, `writers/`, `fetchers/`, `epubutils.py`, `cli.py`.
- `calibre-plugin/` — Calibre UI glue, plugin config and resources.
- `included_dependencies/` — vendored third-party packages bundled into the Calibre plugin zip.
- `makeplugin.py` — build helper that zips the plugin and vendored deps into `FanFicFare.zip`.
- `pyproject.toml` — packaging metadata and `fanficfare` console script entry.
- `defaults.ini`, `example.ini`, `calibre-plugin/plugin-defaults.ini` — canonical config locations and examples.
- `tests/` — pytest tests and fixtures (fixtures_* files used by adapter tests).

Big-picture architecture & patterns
- Adapters: each supported site lives in `fanficfare/adapters/adapter_<site>.py`. Adapters register themselves via `fanficfare.adapters.__init__` which imports each adapter module and builds a domain→class map. Use `adapters.getAdapter(config, url)` to get a site-specific adapter instance.
- Writers: output formats are provided by `fanficfare/writers` and selected via `writers.getWriter(format, config, adapter)` in `cli.py`.
- Configuration: uses hierarchical INI-style files. CLI reads `defaults.ini` / `personal.ini` (see `cli.mkParser`). Calibre plugin has its own `plugin-defaults.ini`.
- Vendoring: `included_dependencies/` contains copies of some libraries so the Calibre plugin can work without system packages. `makeplugin.py` packages these into the plugin zip. Be careful when modifying dependency versions — keep compatibility with the vendored layout.

Developer workflows (run / test / build)
- Dev install and run CLI (editable):
  - `python -m pip install -e .` then `fanficfare --help` or `python -m fanficfare.cli --help`
- Run CLI directly (no install):
  - `python -m fanficfare.cli <options> STORYURL`
- Run tests (pytest):
  - `pytest -q tests/`
  - Tests rely on fixtures files under `tests/fixtures_*.py` — examine these when writing adapter tests.
- Build the Calibre plugin zip:
  - From repo root: `python makeplugin.py` — produces `FanFicFare.zip` by zipping `calibre-plugin/`, `included_dependencies/`, and `fanficfare/` contents.

Project-specific conventions & gotchas
- Adapter naming and registration: add a new adapter as `adapter_<sitename>.py` and ensure it defines `getClass()` and `getAcceptDomains()` as other adapters do. The adapter module must be imported in `fanficfare/adapters/__init__.py` for auto-registration.
- Local copy of `six`: the project ships `fanficfare/six.py` — do not replace it blindly.
- Vendored deps: `included_dependencies/` is used for the Calibre plugin; keep paths and filenames stable for `makeplugin.py` to include them correctly.
- Config precedence: CLI loads multiple `-c/--config` files plus `~/.fanficfare/personal.ini`. Plugin uses `calibre-plugin/plugin-defaults.ini`.
- Translations: `.po` files live under `calibre-plugin/translations/` — plugin loads them via Calibre's translation mechanism.

Integration points to inspect when changing behavior
- `fanficfare/adapters/__init__.py` — adapter discovery and mapping (domain → adapter class).
- `fanficfare/cli.py` — CLI options parsing, dispatch, and how downloads are invoked.
- `fanficfare/writers/` — how output filenames and writing are implemented (`getWriter`, `getOutputFileName`).
- `calibre-plugin/fff_plugin.py` — UI/Calibre integration, preferences, and how the plugin calls into the library.

Examples (useful commands)
- Run a single download (dry-run metadata):
  - `python -m fanficfare.cli --meta-only https://example.com/story`
- Build the Calibre plugin zip:
  - `python makeplugin.py`
- Run site examples list (shows adapter examples):
  - `python -m fanficfare.cli --sites-list`

If anything here is unclear or you'd like more detail (for example: a quick recipe for adding a new adapter, test template, or how adapters handle pagination), tell me which area to expand and I will iterate.

Personal fork & PR workflow
- Note: this repository is a personal fork used to test changes before submitting pull requests to the upstream/main project. Use this fork as a staging area for development and local testing.
- Preferred submission flow:
  - Develop and test changes on topic branches in this fork.
  - When ready to submit a clean PR to the upstream repository, squash your work into a single commit and create a branch containing that single commit. Use that branch to open the PR against the main project.
  - Example (local steps):
    - `git checkout -b tmp-work` (work and commit as needed)
    - `git reset --soft $(git merge-base main tmp-work)` and then `git commit -m "Short, descriptive commit message"` to create a single commit (or use `git rebase -i` to squash)
    - `git checkout -b single-commit-branch` && `git push origin single-commit-branch` and open the PR from that branch.

If you'd like, I can add a small `CONTRIBUTING.md` snippet showing these commands and a checklist to follow before opening a PR.
