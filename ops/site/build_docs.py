"""
Build the documentation site from the Markdown in docs/.

The site is plain static HTML. There is no client-side rendering, so a page is
readable before any script runs and stays readable if none ever does.

The source of truth is the same Markdown the repository ships, so the published
documentation cannot drift away from the documentation a developer reads in the
checkout. Mermaid blocks are kept as ``<pre class="mermaid">`` and rendered by
the one script the page loads.

Usage:
    python -m ops.site.build_docs                 # writes web/docs-dist
    python -m ops.site.build_docs --out somewhere
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from markdown_it import MarkdownIt

from ops.paths import ROOT

DOCS = ROOT / "docs"

#: The navigation, in order. The key is the directory under docs/, so a new
#: page appears in the right group by being saved in the right folder. Only the
#: label is written by hand; anything on disk that is not listed still gets
#: built and appears under "More", so a new file is never silently dropped.
SECTIONS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("Getting started", "getting-started", [
        ("project.md", "What Spark is"),
        ("dashboard.md", "The dashboard"),
        ("cli.md", "Command line"),
    ]),
    ("Using Spark", "using-spark", [
        ("dataset.md", "Your data"),
        ("training.md", "Training your own model"),
        ("model.md", "The models"),
        ("evaluation.md", "Results and limits"),
    ]),
    ("Developers", "developers", [
        ("api.md", "REST API"),
        ("sdk.md", "Python and Node SDKs"),
        ("auth.md", "Sign in"),
    ]),
    ("Running it", "operations", [
        ("deployment.md", "Deployment"),
        ("ci.md", "Releases and CI"),
    ]),
]

STYLE = '\n/* Measured from the reference: black ground, near-white ink, one red accent. */\n:root {\n  --bg: #000000;\n  --panel: #0b0b0c;\n  --text: #f5f5f6;\n  --muted: rgba(245, 245, 246, 0.62);\n  --faint: rgba(245, 245, 246, 0.40);\n  --border: rgba(245, 245, 246, 0.12);\n  --accent: rgb(205, 28, 24);\n  --code-bg: #0d0d0e;\n  color-scheme: dark;\n}\n\n* { box-sizing: border-box; }\n\nbody {\n  margin: 0;\n  background: var(--bg);\n  color: var(--text);\n  font-family: Mulish, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;\n  font-size: 15px;\n  line-height: 1.65;\n  -webkit-font-smoothing: antialiased;\n}\n\na { color: var(--accent); text-decoration: none; }\na:hover { text-decoration: underline; }\n\n/* Top bar */\n.top {\n  position: sticky; top: 0; z-index: 40;\n  display: flex; align-items: center; gap: 28px;\n  height: 60px; padding: 0 24px;\n  background: rgba(0, 0, 0, 0.86);\n  backdrop-filter: blur(10px);\n  border-bottom: 1px solid var(--border);\n}\n.top .brand img { height: 17px; width: auto; display: block; }\n.top nav { display: flex; gap: 22px; }\n.top nav a {\n  color: var(--muted); font-size: 13.5px; font-weight: 600;\n}\n.top nav a:hover { color: var(--text); text-decoration: none; }\n.top .spacer { flex: 1; }\n.top .search {\n  display: flex; align-items: center; gap: 8px;\n  height: 36px; padding: 0 12px; min-width: 260px;\n  border: 1px solid var(--border); border-radius: 8px;\n  color: var(--faint); font-size: 13px; background: var(--panel);\n}\n.top .search kbd {\n  margin-left: auto; font: inherit; font-size: 11px;\n  border: 1px solid var(--border); border-radius: 4px; padding: 1px 5px;\n}\n.top .cta {\n  height: 36px; display: inline-flex; align-items: center; padding: 0 14px;\n  border: 1px solid var(--border); border-radius: 6px;\n  font-size: 12.5px; font-weight: 700; color: var(--text);\n}\n\n/* Three column shell */\n.shell {\n  display: grid;\n  grid-template-columns: 268px minmax(0, 1fr) 244px;\n  gap: 40px;\n  max-width: 1500px;\n  margin: 0 auto;\n  padding: 0 24px;\n  align-items: start;\n}\n\n/* Left navigation */\n.side {\n  position: sticky; top: 60px;\n  max-height: calc(100vh - 60px);\n  overflow-y: auto;\n  padding: 28px 0 64px;\n}\n.side .group {\n  margin: 22px 0 8px;\n  font-size: 10.5px; font-weight: 800; letter-spacing: 1.68px;\n  text-transform: uppercase; color: var(--faint);\n}\n.side .group:first-child { margin-top: 0; }\n.side ul { list-style: none; margin: 0; padding: 0; }\n.side li a {\n  display: block; padding: 7px 10px; border-radius: 8px;\n  font-size: 14px; color: var(--muted);\n}\n.side li a:hover { background: rgba(245, 245, 246, 0.05); color: var(--text); text-decoration: none; }\n.side li a[aria-current="page"] {\n  background: rgba(245, 245, 246, 0.08); color: var(--text); font-weight: 700;\n}\n\n/* Article */\nmain { padding: 34px 0 96px; min-width: 0; }\n.crumb { font-size: 13px; color: var(--faint); margin-bottom: 14px; }\n.crumb a { color: var(--faint); }\n\nh1 {\n  margin: 0 0 14px;\n  font-size: 44px; font-weight: 800; line-height: 1.05; letter-spacing: -1.1px;\n}\nmain > p:first-of-type { font-size: 17px; line-height: 1.62; color: var(--muted); }\n\nh2 {\n  margin: 44px 0 14px; padding-top: 4px;\n  font-size: 26px; font-weight: 800; line-height: 1.5; letter-spacing: -0.65px;\n  scroll-margin-top: 76px;\n}\nh3 {\n  margin: 30px 0 10px;\n  font-size: 18px; font-weight: 700; letter-spacing: -0.2px;\n  scroll-margin-top: 76px;\n}\nmain p { color: var(--muted); }\nmain strong { color: var(--text); }\n\nhr { border: 0; border-top: 1px solid var(--border); margin: 26px 0; }\n\n/* The reference marks list items with a short dash rather than a disc. */\nmain ul { list-style: none; padding-left: 0; }\nmain ul li { position: relative; padding-left: 22px; margin: 8px 0; color: var(--muted); }\nmain ul li::before {\n  content: ""; position: absolute; left: 0; top: 13px;\n  width: 11px; height: 1px; background: var(--faint);\n}\nmain ol { padding-left: 20px; }\nmain ol li { margin: 8px 0; color: var(--muted); }\n\ncode {\n  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;\n  font-size: 12.5px;\n  background: var(--code-bg);\n  border: 1px solid var(--border);\n  border-radius: 5px;\n  padding: 1.5px 5px;\n  color: var(--text);\n}\npre {\n  background: var(--code-bg);\n  border: 1px solid var(--border);\n  border-radius: 10px;\n  padding: 16px 18px;\n  overflow-x: auto;\n  font-size: 12.5px;\n  line-height: 1.7;\n}\npre code { background: none; border: 0; padding: 0; font-size: inherit; }\n\ntable { border-collapse: collapse; width: 100%; font-size: 13.5px; margin: 18px 0; display: block; overflow-x: auto; }\nth, td { border-bottom: 1px solid var(--border); padding: 9px 12px; text-align: left; }\nth { font-weight: 700; color: var(--text); }\ntd { color: var(--muted); }\n\nblockquote {\n  margin: 18px 0; padding: 12px 16px;\n  border-left: 2px solid var(--accent);\n  background: var(--panel);\n  border-radius: 0 8px 8px 0;\n  color: var(--muted);\n}\n\n/* Right rail */\n.rail {\n  position: sticky; top: 60px;\n  max-height: calc(100vh - 60px);\n  overflow-y: auto;\n  padding: 34px 0 64px;\n  font-size: 13px;\n}\n.rail .label {\n  font-size: 10.5px; font-weight: 800; letter-spacing: 1.68px;\n  text-transform: uppercase; color: var(--faint); margin-bottom: 10px;\n}\n.rail ul { list-style: none; margin: 0 0 26px; padding: 0; }\n.rail li a {\n  display: block; padding: 5px 0 5px 12px;\n  border-left: 2px solid transparent;\n  color: var(--muted); font-size: 13px;\n}\n.rail li a:hover { color: var(--text); text-decoration: none; }\n.rail li a.active { border-left-color: var(--accent); color: var(--accent); }\n.rail li.sub a { padding-left: 24px; font-size: 12.5px; }\n.rail .actions { border-top: 1px solid var(--border); padding-top: 16px; }\n.rail .actions button, .rail .actions a {\n  display: flex; align-items: center; gap: 9px;\n  width: 100%; padding: 7px 0; background: none; border: 0;\n  color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer;\n  text-align: left;\n}\n.rail .actions button:hover, .rail .actions a:hover { color: var(--text); text-decoration: none; }\n.rail .actions svg { width: 14px; height: 14px; flex: none; opacity: 0.7; }\n\nfooter {\n  margin-top: 56px; padding-top: 20px;\n  border-top: 1px solid var(--border);\n  font-size: 12.5px; color: var(--faint);\n}\n\n@media (max-width: 1180px) {\n  .shell { grid-template-columns: 240px minmax(0, 1fr); }\n  .rail { display: none; }\n}\n@media (max-width: 860px) {\n  .shell { grid-template-columns: minmax(0, 1fr); gap: 0; }\n  .side { position: static; max-height: none; border-bottom: 1px solid var(--border); padding-bottom: 20px; }\n  .top nav { display: none; }\n  .top .search { min-width: 0; flex: 1; }\n  h1 { font-size: 34px; letter-spacing: -0.8px; }\n  h2 { font-size: 22px; }\n}\n'

PAGE = '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{title} | Spark documentation</title>\n<link rel="icon" href="/favicon.ico" sizes="any">\n<link rel="icon" type="image/png" sizes="32x32" href="/favicon/favicon-32x32.png">\n<link rel="icon" type="image/png" sizes="16x16" href="/favicon/favicon-16x16.png">\n<link rel="icon" type="image/png" sizes="48x48" href="/favicon/favicon-48x48.png">\n<link rel="icon" type="image/png" sizes="192x192" href="/favicon/favicon-192x192.png">\n<link rel="apple-touch-icon" sizes="180x180" href="/favicon/favicon-180x180.png">\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link href="https://fonts.googleapis.com/css2?family=Mulish:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">\n<style>{style}</style>\n</head>\n<body>\n\n<header class="top">\n  <a class="brand" href="/"><img src="/brand/spark-banner-dark.png" alt="Spark"></a>\n  <nav>\n    <a href="project.html">Product</a>\n    <a href="dataset.html">Data</a>\n    <a href="api.html">Reference</a>\n    <a href="deployment.html">Running it</a>\n  </nav>\n  <span class="spacer"></span>\n  <label class="search" for="docsearch">\n    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" width="14" height="14"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>\n    <input id="docsearch" placeholder="Search docs" style="all:unset;flex:1;min-width:0;color:var(--text)">\n    <kbd>/</kbd>\n  </label>\n  <a class="cta" href="https://spark.spacesdrive.cc/">Open the dashboard</a>\n</header>\n\n<div class="shell">\n  <aside class="side">{nav}</aside>\n\n  <main>\n    <p class="crumb">{crumb}</p>\n    {body}\n    <footer>\n      Part of Spark. Every number in this documentation was measured, not\n      estimated.\n    </footer>\n  </main>\n\n  <aside class="rail">\n    <p class="label">On this page</p>\n    {toc}\n    <div class="actions">\n      <button type="button" data-copy-md>\n        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/></svg>\n        <span>Copy as Markdown</span>\n      </button>\n      <button type="button" data-copy-link>\n        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/></svg>\n        <span>Copy link to page</span>\n      </button>\n      <a href="https://github.com/spacesdrive/spark">\n        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>\n        <span>View the source</span>\n      </a>\n    </div>\n  </aside>\n</div>\n\n<script type="module">\n  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";\n  mermaid.initialize({{ startOnLoad: true, theme: "dark" }});\n</script>\n\n<script>\n  /*\n    Mark the contents entry for the section being read.\n\n    An IntersectionObserver over a narrow band was the obvious approach and the\n    wrong one: between two headings no section sits inside the band, so the\n    marker blinks off, and where two headings are close together both are\n    inside it and the marker jumps. This measures every heading against a fixed\n    line below the header and takes the last one above it, which always yields\n    exactly one answer and moves in step with the scroll. Reads are batched\n    into a frame so scrolling stays cheap.\n  */\n  const links = [...document.querySelectorAll(".rail li a")];\n  const targets = links\n    .map((a) => ({{ link: a, el: document.getElementById(a.hash.slice(1)) }}))\n    .filter((t) => t.el);\n\n  if (targets.length) {{\n    let current = null;\n    let queued = false;\n\n    const measure = () => {{\n      queued = false;\n      const line = 96;\n      let active = targets[0];\n      for (const t of targets) {{\n        if (t.el.getBoundingClientRect().top <= line) active = t;\n        else break;\n      }}\n      // The last section can never reach the line at the very bottom, so it\n      // takes over once the page is scrolled to the end.\n      if (innerHeight + scrollY >= document.body.scrollHeight - 2) {{\n        active = targets[targets.length - 1];\n      }}\n      if (active === current) return;\n      current && current.link.classList.remove("active");\n      active.link.classList.add("active");\n      current = active;\n    }};\n\n    const onScroll = () => {{\n      if (queued) return;\n      queued = true;\n      requestAnimationFrame(measure);\n    }};\n\n    addEventListener("scroll", onScroll, {{ passive: true }});\n    addEventListener("resize", onScroll);\n    measure();\n  }}\n\n  // The two copy actions. Both fall back to a selection copy where the\n  // clipboard API is unavailable, and say so if even that fails.\n  async function copy(text, button) {{\n    const label = button.querySelector("span");\n    const original = label.textContent;\n    let ok = false;\n    try {{\n      await navigator.clipboard.writeText(text);\n      ok = true;\n    }} catch {{\n      const field = document.createElement("textarea");\n      field.value = text;\n      field.style.position = "fixed";\n      field.style.opacity = "0";\n      document.body.appendChild(field);\n      field.select();\n      try {{ ok = document.execCommand("copy"); }} catch {{ ok = false; }}\n      field.remove();\n    }}\n    label.textContent = ok ? "Copied" : "Press Ctrl and C";\n    setTimeout(() => {{ label.textContent = original; }}, 1600);\n  }}\n\n  const md = document.getElementById("page-markdown");\n  document.querySelector("[data-copy-md]")?.addEventListener("click", (e) =>\n    copy(md ? md.textContent : document.querySelector("main").innerText, e.currentTarget)\n  );\n  document.querySelector("[data-copy-link]")?.addEventListener("click", (e) =>\n    copy(location.href, e.currentTarget)\n  );\n\n  // "/" focuses search, as the reference does.\n  document.addEventListener("keydown", (e) => {{\n    if (e.key === "/" && document.activeElement?.id !== "docsearch") {{\n      e.preventDefault();\n      document.getElementById("docsearch")?.focus();\n    }}\n  }});\n</script>\n</body>\n</html>\n'


def anchor(text: str) -> str:
    """A stable id for a heading, from its own words."""
    cleaned = re.sub(r"<[^>]+>", "", text)
    cleaned = html.unescape(cleaned).lower()
    cleaned = re.sub(r"[^a-z0-9\s-]", "", cleaned)
    return re.sub(r"\s+", "-", cleaned).strip("-") or "section"


def add_anchors(body: str) -> tuple[str, list[tuple[int, str, str]]]:
    """
    Give every h2 and h3 an id, and report them for the contents list.

    Ids are made unique by suffixing repeats, because two sections in one page
    can legitimately share a name and a duplicate id would send both contents
    entries to the same place.
    """
    seen: dict[str, int] = {}
    found: list[tuple[int, str, str]] = []

    def tag(match: re.Match) -> str:
        level = int(match.group(1))
        inner = match.group(2)
        base = anchor(inner)
        seen[base] = seen.get(base, 0) + 1
        ident = base if seen[base] == 1 else f"{base}-{seen[base]}"
        found.append((level, ident, re.sub(r"<[^>]+>", "", inner)))
        return f'<h{level} id="{ident}">{inner}</h{level}>'

    body = re.sub(r"<h([23])>(.*?)</h\1>", tag, body, flags=re.S)
    return body, found


def build_toc(headings: list[tuple[int, str, str]]) -> str:
    """The right rail contents list. Empty when a page has no sections."""
    if not headings:
        return ""
    rows = []
    for level, ident, text in headings:
        cls = ' class="sub"' if level == 3 else ""
        rows.append(f'<li{cls}><a href="#{ident}">{html.escape(text.strip())}</a></li>')
    return "<ul>" + "".join(rows) + "</ul>"


def crumb_for(filename: str) -> str:
    """Which group a page sits in, shown above its title."""
    for heading, _folder, group in SECTIONS:
        for name, label in group:
            if name == filename:
                return (
                    f"{html.escape(heading)} / "
                    f"<span>{html.escape(label)}</span>"
                )
    return "Documentation"


def slug(filename: str) -> str:
    return filename.replace(".md", "").lower() + ".html"


def render(markdown_text: str) -> str:
    """
    Markdown to HTML, with mermaid fences left for the browser to draw.

    ``markdown_it`` escapes fenced code by default, which would turn a diagram
    into a wall of text, so those blocks are pulled out first and put back
    afterwards.
    """
    diagrams: list[str] = []

    def stash(match: re.Match) -> str:
        diagrams.append(match.group(1))
        return f"\n\nMERMAIDPLACEHOLDER{len(diagrams) - 1}\n\n"

    text = re.sub(r"```mermaid\n(.*?)```", stash, markdown_text, flags=re.S)

    md = MarkdownIt("commonmark", {"html": False, "linkify": True})
    md.enable("table")
    out = md.render(text)

    for i, diagram in enumerate(diagrams):
        out = out.replace(
            f"<p>MERMAIDPLACEHOLDER{i}</p>",
            f'<pre class="mermaid">{html.escape(diagram)}</pre>',
        )

    # Links between documents point at the built pages, not the Markdown.
    out = re.sub(r'href="([A-Za-z_]+)\.md"', lambda m: f'href="{slug(m.group(1) + ".md")}"', out)
    out = re.sub(r'href="docs/([A-Za-z_]+)\.md"', lambda m: f'href="{slug(m.group(1) + ".md")}"', out)
    return out


def build_nav(current: str, pages: dict[str, str]) -> str:
    listed = {f for _, _folder, group in SECTIONS for f, _ in group}
    extra = [(f, f.replace(".md", "").title()) for f in sorted(pages) if f not in listed]
    sections = SECTIONS + ([("More", "", extra)] if extra else [])

    parts = []
    for heading, _folder, group in sections:
        items = [g for g in group if g[0] in pages]
        if not items:
            continue
        parts.append(f'<p class="group">{html.escape(heading)}</p><ul>')
        for filename, label in items:
            mark = ' aria-current="page"' if filename == current else ""
            parts.append(
                f'<li><a href="{slug(filename)}"{mark}>{html.escape(label)}</a></li>'
            )
        parts.append("</ul>")
    return "".join(parts)


def title_of(markdown_text: str, fallback: str) -> str:
    match = re.search(r"^#\s+(.+)$", markdown_text, re.M)
    return match.group(1).strip() if match else fallback


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "web" / "docs-dist"))
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    pages = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(DOCS.glob("**/*.md"))
        if p.name != "README.md"
    }
    if not pages:
        print("No Markdown found in docs/")
        return 1

    for filename, text in pages.items():
        body, headings = add_anchors(render(text))
        # The raw Markdown travels with the page so the copy action hands over
        # the source rather than a flattened version of the rendering.
        body += (
            '<script type="text/plain" id="page-markdown">'
            + html.escape(text)
            + "</script>"
        )
        page = PAGE.format(
            title=html.escape(title_of(text, filename)),
            style=STYLE,
            nav=build_nav(filename, pages),
            crumb=crumb_for(filename),
            toc=build_toc(headings),
            body=body,
        )
        (out / slug(filename)).write_text(page, encoding="utf-8")

    # The landing page is the project overview.
    home = "project.md" if "project.md" in pages else sorted(pages)[0]
    (out / "index.html").write_text(
        (out / slug(home)).read_text(encoding="utf-8"), encoding="utf-8"
    )

    # The logo and the favicon are the dashboard's, copied rather than linked
    # so the documentation site is self-contained and can be served alone.
    for folder in ("brand", "favicon"):
        src = ROOT / "web" / "public" / folder
        if not src.exists():
            continue
        dest = out / folder
        dest.mkdir(exist_ok=True)
        for item in src.iterdir():
            if item.is_file():
                dest.joinpath(item.name).write_bytes(item.read_bytes())

    # Requested by name whether or not a page declares it, so it has to sit at
    # the root rather than inside the favicon directory.
    ico = ROOT / "web" / "public" / "favicon.ico"
    if ico.exists():
        (out / "favicon.ico").write_bytes(ico.read_bytes())

    print(f"built {len(pages)} pages into {out.name}/")
    for filename in sorted(pages):
        print(f"  {slug(filename)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
