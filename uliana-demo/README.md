# ULIANA prototype

A local-first presentation prototype for Skoltech Team 10. It combines a polished concept animation with an interactive, qualitative recorded-session review.

## Run locally

Requirements: Node.js 22.13 or newer.

```bash
npm ci
npm run dev
```

Open the local address printed by the development server (normally `http://localhost:5173`).

For a production check:

```bash
npm run build:static
```

The static site is written to `dist/client`.

## Dashboard scope

The dashboard uses bundled demo data so the interaction can be reviewed without a backend. It supports:

- choosing any repetition in the set;
- switching between overview, movement and hand-zone views;
- scrubbing and playing the illustrative clip;
- downloading a plain-text demo summary.

The demo observations are qualitative and illustrative. The interface does not claim live coaching, injury prevention, fatigue detection, a full-surface pressure mat, validated 360-degree capture or measured force values. Replace the demo dataset in `lib/demo-session.ts` with the evaluated pipeline output before presenting it as a real recorded session.

## Static deployment with GitHub Pages

This folder lives inside the `TEAM_10` monorepo and is published by the workflow at the
repository root: `.github/workflows/deploy-pages.yml`. GitHub only reads workflows from
`/.github/workflows/` at the repository root, so keep the deploy workflow there (the copy
next to this README only applies if this folder is extracted into its own repository).

Steps:

1. Use `main` as the default branch.
2. In **Settings → Pages → Build and deployment**, choose **GitHub Actions**.
3. Push to `main`, or run **Deploy ULIANA prototype** manually from the Actions tab.

The workflow installs locked dependencies inside `uliana-demo`, prefixes static assets with the
repository path, **flattens the asset-prefix directory** and uploads `uliana-demo/dist/client`.
No runtime server, database or secret is required.

### Why the flatten step exists

This build's `assetPrefix` handling mirrors the configured prefix to disk, so a build with
`STATIC_ASSET_PREFIX=/<repo>` writes assets to `dist/client/<repo>/_next/`. A GitHub Pages
project site is already served under `/<repo>/`, which would double the path to
`/<repo>/<repo>/_next/`. Moving `dist/client/<repo>/_next` to `dist/client/_next` before upload
keeps the URL contract (`index.html` still references `/<repo>/_next/...`) while the file layout
matches what Pages serves.

### Private repository caveat

GitHub Pages on the **Free** plan only publishes **public** repositories. For a private
repository you need GitHub Pro/Team/Enterprise, or publish the static output to a host that
supports private repositories on its free tier (Vercel, Netlify or Cloudflare Pages) using build
command `npm run build:static` and output directory `dist/client` — no asset prefix is needed
there because the site is served from the domain root.

### Local production preview

```bash
npm run build:static
python3 -m http.server 8000 --directory dist/client
```

Open `http://localhost:8000`. A prefixed build (as used by Pages) can be previewed the same way
after running the flatten step above.

## Asset and validation notes

See `ASSET-LICENSES.md` for source and licence notes, `EXPORT.md` for scene capture instructions, and `scene-checks/README.md` for the 3D validation record.
