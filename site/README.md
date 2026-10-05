# agentcart.eu static website

The public English-language website is rendered with Python 3.11+ standard
library code. There is no framework, browser JavaScript, cookie, external font
or external resource load. All pages share `src/layout.html`; page bodies live
in `src/pages/`, and local SVG/CSS assets live in `src/assets/`.

`Dockerfile`, `nginx.conf` and `nginx/` build the served image: unprivileged nginx with
security headers and no access logs. `scripts/check-agentcart-site.sh` checks the site, the
image and its chart. Release and DNS cutover steps are in `charts/agentcart-site/README.md`.

## Build and check

Run from the repository root, using an empty output directory:

```sh
python3 site/build.py --out /tmp/agentcart-site
python3 site/check.py /tmp/agentcart-site
```

The optional `--base-url https://agentcart.eu` sets the HTTPS origin used in
canonical links, `robots.txt` and `sitemap.xml`. The default is
`https://agentcart.eu`. Internal navigation uses root-relative trailing-slash
URLs and assets always use `/assets/` URLs. Build refuses a nonempty output
directory rather than leaving stale files mixed with the new tree. Missing
release fields, templates or required assets produce a nonzero exit with a
message. No release metadata is fetched at build time.

The output contains the home, merchants, agents, legal, privacy and 404 pages,
local assets, `robots.txt` and `sitemap.xml`. The 404 page uses the same layout
and absolute asset URLs so it can be served at any unknown path. The sitemap
includes the five public content pages, not the error page.

`check.py` checks all generated HTML, required files, local links and fragments,
resource loads, language and page metadata, release URLs/versions/checksums and
sizes, and prohibited public-site wording. It also checks CSS/SVG resource
references and sitemap consistency. External anchor links are allowed;
canonical links are metadata, not resource loads. The checker reads this
checkout’s `release.json`, not a metadata file inside the output directory.

For a quick local preview:

```sh
python3 -m http.server -d /tmp/agentcart-site
```

Open `http://localhost:8000/`. This simple preview does not reproduce nginx’s
404 handling or its response security headers. The intended server uses
`try_files $uri $uri/ =404` and `error_page 404 /404.html` under:

```text
default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'
```

The deployment configuration is separate from these content sources.

## Deterministic output

Build into two empty directories and compare their complete trees:

```sh
python3 site/build.py --out /tmp/agentcart-site-a
python3 site/check.py /tmp/agentcart-site-a
python3 site/build.py --out /tmp/agentcart-site-b
diff -r /tmp/agentcart-site-a /tmp/agentcart-site-b
```

`diff -r` should print nothing and exit zero. The build injects no timestamps or
random values and copies asset bytes without transformation. Remove the local
output directories when finished.

## Update a published release

`release.json` is the single source of download URLs, tag, version, ZIP sizes
and SHA-256 values. Do not edit rendered HTML or duplicate those values in page
templates.

1. Download the new tag’s `agentcart-release.json` from its GitHub release, for
   example `https://github.com/GiraeffleAeffle/agentcart-tempo-shopbridge/releases/download/v1.24.0/agentcart-release.json`.
2. Set `tag`, `version`, `release_url` and `manifest_url` for that exact tag.
3. Copy the manifest’s `sha256` and `bytes` for `agentcart-shopbridge.zip` into
   `assets.plugin`, and for `shopbridge-direct-skill.zip` into `assets.skill`.
   Set each asset’s name and release download URL. Do not copy local build
   checksums or reuse the previous release’s sizes.
4. Compare that tag’s plugin `readme.txt`, skill `SKILL.md` and purchase-readiness
   reference against the content claims. `git show TAG:PATH` can be used when
   the tag is present locally; otherwise use the published GitHub tag’s raw
   file. Review every “in the next release” label and command-availability row
   before promoting a capability to downloadable-release status.
5. Build, run the checker and compare two builds as above. Review the download
   panels and the release footer before publication.

The current pinned release is v1.24.0. Its plugin ZIP extracts to
`agentcart-shopbridge/`; its skill ZIP extracts to `shopbridge-direct-skill/`
with `SKILL.md`, `references/`, `agents/openai.yaml` and `scripts/`. The verified
x402 v2 Base Sepolia USDC flow and stricter checkout-origin/payment-destination
binding are deliberately labelled as next-release features, not capabilities
of these downloads.

## Content and accessibility maintenance

Keep merchant and buyer claims tied to the repository’s README, CONTEXT,
plugin readme, buyer/merchant setup guides, settlement/verifier contracts,
technical status, production gates and skill instructions. Status snapshots
can lag code and staging evidence: do not turn implementation into a claim of
production validation. Legal and privacy details are supplied by the site
operator, not inferred from plugin behavior.

The only documented harness locations are Claude Code personal/project skills
(`~/.claude/skills/`, `.claude/skills/`) from
<https://code.claude.com/docs/en/skills#where-skills-live>, and Codex
personal/repository skills (`~/.agents/skills/`, `.agents/skills/`) from
<https://developers.openai.com/codex/skills/>. The latter currently redirects
to OpenAI’s skill authoring documentation. Do not add other harness paths
without checking their primary documentation.

Use the shared navigation and skip link, one h1 per page, semantic landmarks,
visible keyboard focus, descriptive links and scrollable tables. The CSS is
mobile-first; prose is limited to 72ch. System fonts and local SVGs avoid
third-party loads. Light-mode text uses ink `#172027`, muted `#5e6a66` and teal
`#0a6c60` against white or `#f4f7f6`; dark-mode text uses light ink, muted and
teal variants against `#131d19` or `#1c2923`. The header wordmark is text in the
accent colour, so it follows the colour scheme. Preserve WCAG AA text contrast
when changing these colors.
