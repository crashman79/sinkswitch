# Submitting SinkSwitch to Flathub

Official reference: [Flathub — Submission](https://docs.flathub.org/docs/for-app-authors/submission/) and [Requirements](https://docs.flathub.org/docs/for-app-authors/requirements).

## Upstream (this repository)

Before opening the Flathub PR:

1. **Metadata** — `flatpak/io.github.crashman79.sinkswitch.metainfo.xml` must satisfy [AppStream requirements](https://docs.flathub.org/docs/for-app-authors/requirements), including screenshots. The default screenshot URL is  
   `https://raw.githubusercontent.com/crashman79/sinkswitch/main/docs/flathub/main-window.png` — keep that file on `main` after you change it.
2. **Build locally** — From repo root, install Freedesktop 24.08 runtime/SDK and run `flatpak-builder` against `flatpak/io.github.crashman79.sinkswitch.yml` (or use [org.flatpak.Builder](https://docs.flathub.org/docs/for-app-authors/submission#build-and-install) as in the docs).
3. **Linter** — Run before the PR (requires `org.flatpak.Builder`):

   ```bash
   flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest flatpak/io.github.crashman79.sinkswitch.yml
   ```

   Fix reported issues or request [exceptions](https://docs.flathub.org/docs/for-app-authors/linter#exceptions) only when appropriate.

## Manifest for Flathub (often different from this repo)

Flathub builds typically **must not use network during the build**. This repo’s manifest uses `pip3 install` with `--share=network` for convenience. For the **Flathub submission**, maintain a manifest in your Flathub fork that:

- Adds Python wheels via [flatpak-pip-generator](https://github.com/flathub/flatpak-builder-tools/tree/master/pip) (pinned URLs + SHA256), **or** equivalent vendored sources.
- Omits `build-options: build-args: --share=network` on the app module unless Flathub reviewers allow it.
- Points `sources` at a **tag** (or tarball) of this repo, not a moving branch, for reproducibility.

## Submission PR on GitHub (exact process)

Do **not** open the PR against `master` on [flathub/flathub](https://github.com/flathub/flathub).

1. **Fork** [flathub/flathub](https://github.com/flathub/flathub) with **“Copy the `master` branch only” unchecked** (per Flathub docs).
2. **Clone** your fork and use the **`new-pr` branch**:

   ```bash
   git clone --branch=new-pr git@github.com:YOUR_GITHUB_USERNAME/flathub.git
   cd flathub
   ```

3. **Create** a submission branch from `new-pr`:

   ```bash
   git checkout -b sinkswitch-submission new-pr
   ```

4. **Add** the required files (usually `io.github.crashman79.sinkswitch.yml` or `io.github.crashman79.sinkswitch.json` plus any extra-data or modules Flathub needs). Commit and push this branch.

5. On GitHub: open a **pull request** with **base `new-pr`** (not `master`), **compare** your `sinkswitch-submission` branch.

6. **Title** the PR: `Add io.github.crashman79.sinkswitch` (see Flathub template).

7. **Review** — Address reviewer comments in the same PR (no need to close/reopen). When asked, comment on the PR: **`bot, build`** to trigger a test build.

## After approval

Reviewers merge into a new repo under the Flathub org; you get a maintainer invite (**2FA** required). Further releases are updates in **that** app repo, not another full submission — see [App maintenance](https://docs.flathub.org/docs/for-app-authors/maintenance).

## App ID

`io.github.crashman79.sinkswitch` matches `flatpak/io.github.crashman79.sinkswitch.desktop` and the Metainfo `<id>`.
