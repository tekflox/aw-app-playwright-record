# aw-app-template

Starting point for a new AW workspace app (`aw-app.json` manifest schema v1).
Every `aw-app-*` app should be born
from **the latest version of this template**, not copy-pasted from an
existing app — this repo already carries the full, currently-correct
skeleton: manifest, plugin, tests, and a CI/CD pipeline wired to the
`tekflox/aw-marketplace` release + catalog-sync automation, including every
fix that's landed on that pipeline so far (test-gating before release,
correct permissions ceiling, auto-merge).

It's a real, working app — not just files. `aw-app-template` installs one trivial `template` CLI
that prints a configurable greeting, contributes a tiny backend sub-app
(`GET /template` + `WS /ws/echo` inside the app mount) and a frontend bundle (with a
`core.nav` slot component written out but commented out — see `ui/src/plugin.js`
— so the template adds no stray pill to a real workspace's nav), and runs
standalone too (`python -m template_app`) — so cloning this template and
pushing to `master` gives you a green CI run, a tagged release, and a
marketplace catalog entry before you've changed a single line. See
`docs/knowledge_base/docs/architecture/adr-app-front-back-routes-dual-mode.md`
(Decision 6) for the design this scaffold implements.

## Use this template

GitHub's **"Use this template"** button (top of the repo page) creates a
new repo seeded from this one's current `master` — no git history, no fork
relationship, just a fresh copy. From the CLI:

```bash
gh repo create tekflox/aw-app-<yourapp> --template tekflox/aw-app-template --public
git clone https://github.com/tekflox/aw-app-<yourapp>
```

Then rename everything marked **TEMPLATE** in comments and every
`aw-app-template`/`template`/`template_app` occurrence — the scaffold names
its app, its CLI, its route and its Python package after itself, so replacing
"template" with your app's name everywhere is the whole rename:

1. **`aw-app.json`** — `id`, `name`, `description`, `runtime.entrypoint`,
   `contributes.system_clis`, `config_schema` (or delete it if your app has
   no config knobs at all). This template ships `config_visible: false` —
   not every app has *user-facing* settings (a Runnables-style app with
   nothing to configure, for instance), so the Settings gear/entry stays
   hidden even though the `greeting` config_schema is real and read via
   `ctx.config`. Flip `config_visible` to `true` (or delete the field — it
   defaults `true`) once your app has settings worth exposing in the UI —
   see `aw-app-git`'s manifest for a config-schema example with the gear on.
2. **`template_app/`** — rename the directory + the class in `plugin.py`
   (and update `runtime.entrypoint` in `aw-app.json` to match). Keep,
   change, or delete each piece independently — they're not all-or-nothing:
   - `installer.py` / `scripts/` — the `template` CLI install pattern
     (`commands:install`). Delete if your app has no CLI.
   - `routes.py` / `plugin.py`'s `ctx.routes.register(...)` — the backend
     sub-app pattern (`routes:register`, GET + WS). Delete if your app has
     no backend routes.
   - `__main__.py` — the standalone-mode entry (`python -m <pkg>`). Delete
     if your app only ever runs integrated.
   - See the **`aw-create-app`** skill (`skills/aw-create-app/SKILL.md`,
     §5–§8) for the full backend-routes / frontend-code / standalone
     contract, or a sibling app for a bigger example of one piece:
     - `aw-app-git` — a settings panel + OAuth device-flow login route.
     - `aw-app-whiteboard` — `contributes.nav` + `contributes.frontend`
       (a top-nav entry + window), `db:own-tables`.
     - `aw-app-devctl` — `routes:register` talking CDP to another app's
       container.
     - `aw-app-browser` — `tier: container` (Tier-2, a sidecar container
       instead of in-process Python).
3. **`scripts/`** — replace `install_template.sh` with your app's real
   installer(s) (one script per CLI is the convention, but a single script
   installing several related tools — like `aw-app-essentials`'s Node.js
   toolkit — is fine too). Keep `uninstall.sh` in sync — it's the one
   script the framework's journal reverse-replay calls on uninstall, so it
   must reverse *everything* every `install_*.sh` here does.
4. **`ui/`** — rename `SLUG` in `src/plugin.js`/`src/standalone.js` (and
   `template_app/__main__.py`'s `SLUG`) to match your app's `id`. Delete the
   whole directory (+ `contributes.frontend`/`ui:code`/`ui:slots:*` in
   `aw-app.json`) if your app has no frontend code — a declarative `windows`
   spec doesn't need any of this.
5. **`tests/`** — `validate_manifest.py` needs no changes (fully generic).
   Update `test_installer.py`'s assertions to match your real
   `installer.py` functions, `test_routes.py`/`test_standalone.py` to match
   your real routes, and `standalone_test.sh` to install/check your real
   CLI(s).
6. **`.github/workflows/release.yml`** — no changes needed. It calls
   `tekflox/aw-marketplace`'s shared `app-release.yml`, which runs
   `tests/validate_manifest.py` + `tests/test_*.py` on every push to
   `master` — a failing test stops the release before any version bump,
   tag, or marketplace catalog write happens. **If your repo is NOT under
   the `tekflox` org** (e.g. it lives on your personal account), the
   workflows still need no edit — `runs-on` is derived from the repo owner
   in all three of `release.yml` (via the called workflow), `test.yml` and
   `security-scan.yml` — but you must add `MARKETPLACE_SYNC_TOKEN` as a
   **repo-level** secret on your repo before the release can complete. See
   [CI/CD](#cicd) for the token shape and what a first push looks like
   until it exists.
7. **`README.md`** — replace this file with your app's own (what it
   installs, how it's configured, what's been tested where).

Finally, get your new app **listed** in the marketplace: your first push
past a passing test suite auto-tags a release and opens a
`chore(sync): <id> -> vX.Y.Z` PR against `tekflox/aw-marketplace`'s
`apps.json` (auto-merged for first-party TekFlox sources) — nothing to do
by hand.

## Layout

- `aw-app.json` — the manifest (`id: aw-app-template`, `tier: inprocess`).
- `tests/validate_manifest.py` — runs the same checks CI does, locally.
  The schema is **not** copied into this repo: it lives in aw-marketplace
  (`schemas/aw-app.schema.json`, its permissions pattern generated from
  core's `src/apps/capabilities.py`) and the validator finds it in a sibling
  checkout. 28 repos used to each freeze their own copy; they drifted into 11
  versions, so a green local run said nothing about the release.
- `scripts/install_template.sh` — installs a trivial `template` command into the
  workspace's persistent bin dir (`~/.aw-workspace/bin`, on PATH, survives
  restarts). Idempotent.
- `scripts/uninstall.sh` — reverses it.
- `template_app/plugin.py` — `TemplateAppPlugin` entrypoint; `activate(ctx)`
  installs the CLI via the gated `ctx.commands` facade (capability
  `commands:install`) so it's journaled and the framework reverts it on
  uninstall, and registers `routes.py`'s sub-app via `ctx.routes` (capability
  `routes:register`).
- `template_app/installer.py` — the same install logic as a plain
  subprocess-calling module (no framework `ctx` needed) — used by the tests
  below.
- `template_app/routes.py` — `build_routes() -> FastAPI`, the mode-agnostic
  backend sub-app (`GET /template`, `WS /ws/echo` inside the app mount) shared by integrated mode
  (`plugin.py`) and standalone mode (`__main__.py`) — ADR Decision 2/4/6.
- `template_app/__main__.py` — standalone entrypoint (`python -m
  template_app`): mounts `routes.py`'s sub-app at the same `/api/apps/aw-app-template`
  prefix, serves `ui/dist/` statically, no `IdentityGuard`.
- `ui/` — the frontend half, mode-agnostic (ADR Decision 3/4): `src/client.js`
  is the framework-free core; `src/plugin.js` is the integrated-mode
  `register(host)` entry (a `core.nav` slot component, commented out so the
  template stays invisible in the nav, + a live headless WS client), built by
  Vite in **lib mode** with `react`/`react-dom` externalized
  (`vite.config.js --mode plugin` → `dist/template.js`, referenced from
  `aw-app.json`'s `contributes.frontend.bundle`); `src/standalone.js` +
  `index.html` is the standalone page (`vite.config.js --mode standalone` →
  `dist/index.html` + assets). `npm run build` in `ui/` runs both, into the
  SAME `ui/dist/`.
- `tests/validate_manifest.py` — validates `aw-app.json` against the schema
  + checks every `system_clis` installer path exists on disk.
- `tests/test_installer.py` — unit tests (subprocess mocked, no real
  installs) — runs in CI on every push, gating the release.
- `tests/test_routes.py` — `TestClient` coverage of `routes.py`'s sub-app
  (GET `/template`, WS `/ws/echo`) — runs in CI.
- `tests/test_plugin.py` — `TemplateAppPlugin.activate()`/`deactivate()` against
  a lightweight `ctx` double (no real F4 runtime needed) — runs in CI.
- `tests/test_main.py` — `__main__.py`'s standalone-mode `main()` (the
  "ui/dist not built yet" note, `PORT`/`AW_APP_HOST` env overrides),
  `uvicorn.run` mocked — runs in CI.
- `external-client/app-api-client.js` — generic, dependency-free helper for
  calling your app's API from an external client (browser extension, mobile
  app); see "Calling your app's API from an external client" below.

### Calling your app's API from an external client (browser extension, mobile app, etc.)

Every app installed on an AW workspace is reachable via **two** hostname
shapes, both hitting the exact same backend route/view/auth
(`aw-workspace`'s `src/apps/runtime.py`, `_attach_mount`, registers a
`Mount(f"/api/apps/{app_id}")` **and** a `Host(f"{app_id}.app.{...}")` for
the same guarded ASGI sub-app — generic platform behavior, true for every
installed app, not something you opt into):

1. **Workspace-wide API host** — path-prefixed with your app's slug:
   `https://api.<workspace-slug>.workspace.aw.tekflox.com/api/apps/<app-slug>/<route>`
2. **Per-app subdomain** — bare path, Host-header-routed straight to your
   app's sub-application with no prefix stripped:
   `https://<app-slug>.app.<workspace-slug>.workspace.aw.tekflox.com/<route>`

**Same-origin code in `ui/` never needs to worry about this** — a request
made from a page already loaded on one of those hosts resolves relative
paths against that host automatically. This only matters for a true
**external** caller (browser extension popup, native mobile app, userscript,
CLI) that has a user-configured hostname and builds an absolute URL from it
by hand. If that code hardcodes one shape, it 404s the moment the user
points it at the other host — there's no `/api/apps/<slug>/...` route on the
subdomain-routed mount (only bare paths), and no bare route on the
workspace-wide API host (only prefixed ones).

`external-client/app-api-client.js` is a small, dependency-free, no-build-step
JS helper any external client can copy in to handle this correctly —
`buildAppApiUrl(configuredHost, appSlug, routePath)` detects which shape the
configured host is and returns the right URL either way. See that
directory's `README.md` for usage, and its header comment for the full
rationale (including the real incident it generalizes, in `aw-app-proxy`'s
browser extensions).

### WebSocket namespace rule

Do not claim root `/ws/*` for app features. Root `/ws/*` is reserved for AW
core/control-plane sockets. App-owned browser WebSockets must live in an app
namespace:

- current in-process mount shape: `/api/apps/<slug>/ws/<name>`
- reserved edge namespace for app-owned sockets: `/ws/apps/<slug>/<name>`

When adding a top-level WebSocket route or Caddy/edge mapping for an app, use
`/ws/apps/<slug>/...`, never `/ws/...`.
- `tests/test_standalone.py` — boots `__main__.py`'s standalone app and hits
  the mounted API (plus the static UI mount, once `ui/` is built) — runs in CI.
- `tests/standalone_test.sh` — installs `template` for real and checks
  resolution + output; run inside the aw-workspace container (not part of
  CI — needs the real target environment).

### App window contract

Window definitions live in `contributes.windows[]`, but shared window chrome
lives in `aw-frontend`, not in each app. Full app surfaces should declare a
managed window:

```jsonc
{
  "id": "myapp.main",
  "title": "My App",
  "icon": "box",
  "body": { "type": "managed_app", "kind": "web", "path": "/" }
}
```

Use `body.type: "declarative"` only for focused settings/control panels that
need the widget vocabulary. Managed windows and `tier: "container"` apps also
receive framework-owned settings automatically: `auto_start`,
`auth_required`, and `public`. `aw-frontend` renders those toggles, and
`aw-workspace` persists and enforces them. App packages should not implement
duplicate lifecycle/auth/public toggles. See `docs/window-contract.md`.

## Seeding Tasks and Agents on Install

Two contribution surfaces don't mount something your app owns — they **seed**
an object into a store the user also edits by hand:

| Surface | Ships | Doc | Example |
|---|---|---|---|
| `contributes.tasks` | scheduled work your features depend on | [`docs/contributing-tasks.md`](docs/contributing-tasks.md) | [`examples/contributes-tasks/`](examples/contributes-tasks/) |
| `contributes.agents` | Agents Platform models, configs, groups and agents | [`docs/contributing-agents.md`](docs/contributing-agents.md) | [`examples/contributes-agents/`](examples/contributes-agents/) |

Both are **create-if-absent, never updated, never removed on uninstall** —
so a corrected command or prompt in your *next* version does **not** reach an
installation that already seeded. Read the doc before shipping one; that rule
is the part that surprises people on their second release.

Each example is a complete manifest, not a snippet, so you can run the real
validator against it before merging the relevant part into yours:

```bash
python tests/validate_manifest.py examples/contributes-agents/aw-app.json
```

## Calling the Workspace API From Your App or an MCP

Every workspace has a shared API key (Settings → Integrations → Workspace
API Key) that lets an app or a standalone MCP server authenticate into that
workspace's HTTP API with an `X-Api-Key` header instead of a browser
session — no per-app config field needed. See
`docs/app-workspace-api-auth.md` for the full pattern (in-process vs
external-process reads) and a worked example
(`tekflox/aw-app-whiteboard`'s `mcp_server/`).

## CI/CD

`tests/validate_manifest.py` and `tests/test_*.py` run in
`tekflox/aw-marketplace`'s shared `app-release.yml` reusable workflow on
every push to `master` — a failure stops the release **before** any version
bump, tag, or marketplace catalog sync happens. See that repo's
`scripts/bump_version.py` for the semver-bump-from-commit-messages logic and
`scripts/sync_catalog_entry.py` for what fields get written into
`apps.json` automatically (name/description/publisher/resource_estimate —
`has_config`/`bootstrap`/`icon`/`tags`/`category` are set once by hand on
first listing and not auto-synced afterward).

**If your app repo is not under the `tekflox` org.** Everything above still
applies, and no workflow file needs editing — but two things differ, and one
of them needs a human once:

- **Runners are derived, not configured.** `release.yml` (through the called
  `app-release.yml`), `test.yml` and `security-scan.yml` all resolve
  `runs-on` from `startsWith(github.repository, 'tekflox/')`: inside the org
  you get the `[self-hosted, aw-baremetal]` pair, outside it you get
  `ubuntu-latest`. This is not a preference. An org runner group can only be
  shared with repos *in* that org, so a job aimed at those runners from a
  personal-account repo **queues forever instead of failing** — exactly how
  `aw-app-uc-phd`'s catalog entry stayed frozen at `v0.1.1` while its repo
  reached `v0.6.0`. There is no runner input to pass.
- **`MARKETPLACE_SYNC_TOKEN` must be a repo secret, and it is yours to
  create.** Outside the org there are no org secrets to inherit, so add it
  under *Settings → Secrets and variables → Actions → New repository
  secret*. The smallest safe shape is a **fine-grained PAT** scoped to
  `tekflox/aw-marketplace` (Contents: write, Pull requests: write) plus your
  own app repo (Contents: write) — not a full-scope `admin:org` /
  `delete_repo` PAT. Until it exists, your first push to `master` gives a
  **red** run that fails on `app-release.yml`'s first step and names the repo
  and the secret. That is intended: a red, self-explaining run is the point,
  where an eternally-queued one hides.
- **Your catalog sync PR will not auto-merge.** The auto-merge step in
  `app-release.yml` is gated on `startsWith(github.repository, 'tekflox/')`,
  so a non-org app's `sync/<id>` PR opens and waits for a human. For a
  catalog every workspace reads, a human gate on a non-org contributor is
  correct — **don't try to defeat it**. Ping whoever maintains
  `tekflox/aw-marketplace` to merge it.

One caveat worth knowing: every step in the shared release job is network +
Python today, which is why `ubuntu-latest` is sufficient. If a future step
ever needs the bare-metal host (a Docker build against a local registry,
workspace-local state), it will work for `tekflox/*` apps and fail only for
personally-owned ones.

**Coverage gate — `.github/workflows/test.yml`, blocking, on every push and
PR.** `pytest --cov=template_app` against `pyproject.toml`'s
`[tool.coverage.report] fail_under = 100`, a hard floor (not the estate's
per-repo baseline+ratchet default in `docs/standards/pipeline-testing.md`
§4.2 — this template is what every new `aw-app-*` is born from and is meant
to be the quality bar the rest of the estate is measured against, so it
holds itself to actual 100%, not just the §4.2 new-repo floor of 80%).
Lines that are genuinely impractical to exercise (glue, dunder reprs,
`__main__` guards) are excluded explicitly via `[tool.coverage.report]
exclude_lines`, not left as a silent gap — add a new exclusion there (with a
reason) rather than letting real, reachable code go untested. This gate
lives here rather than in `app-release.yml` because the shared workflow
doesn't have a coverage step yet (that's a separate, later change to
`aw-marketplace`); until it does, copying this template inherits the local
gate too. Keep whatever module you add fully covered, or `fail_under` will
fail the build — it may only be raised, never lowered (a lower value needs
a written reason in the commit message).

**Downloadable coverage report.** The same CI step that enforces the gate
also emits an HTML report (`coverage html` → `htmlcov/`) and a
`coverage.xml`, and `.github/workflows/test.yml` publishes both as a
`coverage-report` artifact via `actions/upload-artifact` (uploaded even when
the gate fails, so a red run still explains itself). To read it: open the
run under this repo's **Actions** tab → the `coverage` job's **Summary**
page → **Artifacts** → download `coverage-report.zip` → unzip and open
`htmlcov/index.html` in a browser for the line-by-line view, or feed
`coverage.xml` to another tool (Cobertura format) — no local `pytest` run
needed just to see what's covered.

## Contributing a skill (`contributes.skills`)

This app ships a **skill** — `skills/aw-create-app/SKILL.md` — that teaches an
agent how to author a new workspace app from this template (manifest, tiers,
the capability catalog, contributes, the window widget vocabulary, install +
marketplace release). It's declared in the manifest:

```jsonc
"contributes": {
  "skills": [
    { "id": "aw-create-app", "path": "skills/aw-create-app/SKILL.md",
      "description": "How to author an aw-workspace app." }
  ]
}
```

Convention for any app that wants to teach an agent how to use it: drop a
`skills/<id>/SKILL.md` (YAML frontmatter with `name` + `description`) and list
it under `contributes.skills`. On install, aw-workspace's runtime symlinks the
skill's own directory into a shared workspace skills index (no content
duplication) and lists it at `GET /api/apps/-/skills`; uninstall removes the
symlink. See `repos/aw-workspace/src/apps/skills.py`.
