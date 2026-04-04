# Submitting SinkSwitch to Flathub

Official reference: [Flathub — Submission](https://docs.flathub.org/docs/for-app-authors/submission/) and [Requirements](https://docs.flathub.org/docs/for-app-authors/requirements).

## Upstream (this repository)

Before opening the Flathub PR:

1. **Metadata** — `flatpak/io.github.crashman79.sinkswitch.metainfo.xml` must satisfy [AppStream requirements](https://docs.flathub.org/docs/for-app-authors/requirements), including screenshots. The default screenshot URL is  
   `https://raw.githubusercontent.com/crashman79/sinkswitch/main/docs/flathub/main-window.png` — keep that file on `main` after you change it.
2. **Build locally** — Install Freedesktop 24.08 runtime/SDK and run `flatpak-builder` against **`flatpak/io.github.crashman79.sinkswitch-flathub.yml`** (or [org.flatpak.Builder](https://docs.flathub.org/docs/for-app-authors/submission#build-and-install)).
3. **Linter** — Run before the PR (requires `org.flatpak.Builder`):

   ```bash
   flatpak run --command=flatpak-builder-lint org.flatpak.Builder manifest flatpak/io.github.crashman79.sinkswitch-flathub.yml
   ```

   Fix reported issues or request [exceptions](https://docs.flathub.org/docs/for-app-authors/linter#exceptions) only when appropriate.

## Manifest for Flathub

Upstream ships **`flatpak/io.github.crashman79.sinkswitch-flathub.yml`**: vendored wheels (no network during `pip`) and a **git** source with a **`commit`** pin on the `sinkswitch` module.

1. Set **`commit`** to the exact upstream Git revision Flathub should build (ideally the release tag on GitHub).
2. Copy the file into your fork as **`io.github.crashman79.sinkswitch/io.github.crashman79.sinkswitch.yml`**.
3. That commit’s tree must include a matching **`<release>`** in `flatpak/io.github.crashman79.sinkswitch.metainfo.xml`.

Wheel modules are edited in **`flatpak/python3-deps.yml`** and duplicated in `-flathub.yml`; refresh steps are in [flatpak/README.md](./README.md#refreshing-flathub-python-wheels).

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

4. **Add** `io.github.crashman79.sinkswitch/io.github.crashman79.sinkswitch.yml` (copy from upstream **`io.github.crashman79.sinkswitch-flathub.yml`**, with **`commit`** set for the release). Commit and push this branch.

5. On GitHub: open a **pull request** with **base `new-pr`** (not `master`), **compare** your `sinkswitch-submission` branch.

6. **Title** the PR: `Add io.github.crashman79.sinkswitch` (see Flathub template).

7. **Review** — Address reviewer comments in the same PR (no need to close/reopen). When asked, comment on the PR: **`bot, build`** to trigger a test build.

## After approval

Reviewers merge into a new repo under the Flathub org; you get a maintainer invite (**2FA** required). Further releases are updates in **that** app repo, not another full submission — see [App maintenance](https://docs.flathub.org/docs/for-app-authors/maintenance).

## App ID

`io.github.crashman79.sinkswitch` matches `flatpak/io.github.crashman79.sinkswitch.desktop` and the Metainfo `<id>`.
