# Interactive architecture

`index.html` is a self-contained, read-only architecture map. It includes the 75
stages and support components from the tailoring engine, clickable descriptions,
animated connections, pause/play, and reduced-motion support. It makes no inference
requests and has no access to candidate data. Selection and playback preferences
are presentation state stored locally in the browser when storage is available.

The README uses `assets/engine-flow.gif` as a moving overview. GitHub Markdown
does not execute script or iframe content, so the full interactive version opens
as a separate page. See [GitHub's Markdown specification](https://github.github.com/gfm/#disallowed-raw-html-extension-).

## Local viewing

Open `docs/index.html` directly in your browser, or serve the directory:

```bash
python3 -m http.server 8000 --directory docs
```

Visit `http://localhost:8000`. This serves the documentation folder only. Stop
the server with Ctrl+C when finished.

## GitHub Pages

The files are prepared locally. No remote publication or Pages setting has been
changed. After publishing the repository yourself:

1. Open the repository on GitHub.
2. Choose **Settings → Pages**.
3. Under **Build and deployment**, select **Deploy from a branch**.
4. Select **main** and **/docs**, then click **Save**.
5. Wait for the deployment and use the site URL shown by GitHub.

This uses GitHub's branch-based publishing configuration; no repository workflow
file is included. `.nojekyll` lets the prepared static files be served directly.
See [GitHub's publishing-source instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

The README currently points to `https://jntnayeemmsbdsa.github.io/CareerOps/`,
the expected project-site address for that owner and repository name. The URL
becomes live only after publication and a successful Pages deployment. If your
owner/name or hosting address differs, replace both architecture links in README.
Fork maintainers should use their own Pages URL.

The static overview is a phase-level summary. The interactive page contains the
full component map. Moving particles illustrate dependency flow; they are not
telemetry, a live application run, or measured throughput.
