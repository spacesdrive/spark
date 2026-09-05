/**
 * Guards on the shared design system.
 *
 * The dashboard drifted into four different button heights and a page title
 * that changed weight between pages, because nothing stopped it. These are
 * cheap checks that read the source and fail when a page invents its own
 * spacing, height or heading instead of using the shared one.
 *
 * They are deliberately about the system, not about any one page. A rule that
 * has to be re-stated per page is a rule that will be forgotten.
 */

import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const PAGES = join(SRC, "pages");

function pageFiles(): string[] {
  return readdirSync(PAGES).filter((f) => f.endsWith(".tsx"));
}

/** Every component source, walked recursively. */
function componentFiles(dir = join(SRC, "components")): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...componentFiles(full));
    else if (entry.name.endsWith(".tsx")) out.push(full);
  }
  return out;
}

function read(path: string): string {
  return readFileSync(path, "utf8");
}

describe("button sizing", () => {
  it("offers exactly three heights, with no half steps", () => {
    const primitives = read(join(SRC, "components/ui/primitives.tsx"));
    const sizes = primitives.slice(
      primitives.indexOf("const SIZES"),
      primitives.indexOf("};", primitives.indexOf("const SIZES"))
    );
    // h-8 = 32, h-9 = 36, h-10 = 40.
    expect(sizes).toContain("h-8");
    expect(sizes).toContain("h-9 ");
    expect(sizes).toContain("h-10");
    // A fractional height is what produced 38px next to 36px.
    expect(sizes).not.toMatch(/h-\d+\.\d/);
  });

  it("does not let anything hand-roll a control height", () => {
    // Pages were the original offenders, but the two worst cases turned out to
    // be in the shared components themselves: Select and Field were both h-9.5,
    // so every form row put a 38px control next to a 36px button. Checking only
    // pages would have missed the ones that affect every page.
    const offenders: string[] = [];
    for (const file of [...pageFiles().map((f) => join(PAGES, f)), ...componentFiles()]) {
      const source = read(file);
      // Only heights in the range a control occupies. A 6px progress bar is
      // not a button, and a rule about buttons should not flag one.
      const matches = (source.match(/h-\d+\.\d+/g) ?? []).filter((m) => {
        const value = Number(m.slice(2));
        return value >= 7 && value <= 12;
      });
      if (matches.length) offenders.push(`${file}: ${matches.join(", ")}`);
    }
    expect(offenders).toEqual([]);
  });
});

describe("page structure", () => {
  it("uses the shared PageHeader rather than a bare h1", () => {
    // Login is a standalone auth screen, not a dashboard page, so it owns its
    // own title treatment rather than a PageHeader with a breadcrumb.
    const exempt = new Set(["Login.tsx"]);
    const offenders: string[] = [];
    for (const file of pageFiles()) {
      if (exempt.has(file)) continue;
      const source = read(join(PAGES, file));
      if (/<h1[\s>]/.test(source)) offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });

  it("gives every page except the root a breadcrumb", () => {
    const exempt = new Set(["Overview.tsx", "Login.tsx"]);
    const missing: string[] = [];
    for (const file of pageFiles()) {
      if (exempt.has(file)) continue;
      const source = read(join(PAGES, file));
      if (!source.includes("<PageHeader")) continue;
      if (!source.includes("breadcrumb=")) missing.push(file);
    }
    expect(missing).toEqual([]);
  });

  it("sets the page title once, in one weight", () => {
    const primitives = read(join(SRC, "components/ui/primitives.tsx"));
    expect(primitives).toContain("text-[24px] font-bold");
  });
});

describe("documentation links", () => {
  it("never points at the hostname whose certificate fails", () => {
    const files = [
      join(SRC, "config/docs.ts"),
      ...pageFiles().map((f) => join(PAGES, f)),
    ];
    for (const file of files) {
      const source = read(file);
      // docs.spark... is two levels deep and not covered by Universal SSL.
      expect(source).not.toMatch(/https:\/\/docs\.spark\.spacesdrive\.cc/);
    }
  });
});

describe("honesty of the interface", () => {
  it("does not claim the SDKs are missing, now that they exist", () => {
    const apiPage = read(join(PAGES, "ApiDocs.tsx"));
    expect(apiPage).not.toMatch(/no Python or Node package yet/i);
    expect(apiPage).not.toMatch(/When SDKs exist/i);
  });

  it("does not still describe training as unavailable", () => {
    for (const file of ["Training.tsx", "Models.tsx"]) {
      const source = read(join(PAGES, file));
      expect(source, file).not.toMatch(/Training is not available yet/i);
      expect(source, file).not.toMatch(/the moment training is enabled/i);
    }
  });
});

describe("the four refactored pages", () => {
  const FOUR = [
    "TestTransaction.tsx",
    "TestDataset.tsx",
    "RiskAnalysis.tsx",
    "AbuseRings.tsx",
  ];

  it("groups content with Section rather than boxing all of it in cards", () => {
    // The complaint was a card for everything. A page that never reaches for
    // Section is almost certainly still a stack of boxes.
    for (const file of FOUR) {
      const source = read(join(PAGES, file));
      expect(source, file).toContain("<Section");
    }
  });

  it("puts the technical terms behind a hover definition", () => {
    for (const file of FOUR) {
      const source = read(join(PAGES, file));
      expect(source, file).toMatch(/HoverPreview|MetricStrip/);
    }
  });

  it("keeps the primary action singular", () => {
    // Two competing solid buttons is what made it unclear what a page was for.
    // Test Transaction does one thing and so has exactly one. Test Dataset is a
    // stepper: it runs the scoring, and later offers the download, which is the
    // primary action of the results stage rather than a rival to the first.
    const expected: Record<string, number> = {
      "TestTransaction.tsx": 1,
      "TestDataset.tsx": 2,
    };
    for (const [file, count] of Object.entries(expected)) {
      const source = read(join(PAGES, file));
      const uses = source.match(/variant="primary"/g) ?? [];
      expect(uses.length, file).toBe(count);
    }
  });

  it("styles buttons with classes that actually exist", () => {
    // A button once shipped using "btn btn-primary", which are defined
    // nowhere, so the most important action on the page rendered as bare text
    // with no background at all. Nothing may reference a class the stylesheet
    // does not define.
    const css = read(join(SRC, "styles/index.css"));
    const sources = [
      ...pageFiles().map((f) => read(join(PAGES, f))),
      ...componentFiles().map((f) => read(f)),
    ].join("\n");
    for (const invented of sources.match(/\bbtn(?:-[a-z]+)?\b/g) ?? []) {
      expect(css, `${invented} is used but never defined`).toContain(
        `.${invented}`
      );
    }
  });
});

describe("evil buttons are used, not merely installed", () => {
  it("wires every one that ships to a real action", () => {
    const buttons = read(join(SRC, "components/ui/ActionButtons.tsx"));
    const exported = [...buttons.matchAll(/export function (\w+)/g)].map(
      (m) => m[1]
    );

    const app = [...pageFiles().map((f) => read(join(PAGES, f)))].join("\n");
    for (const name of exported) {
      expect(app, `${name} is exported but never used`).toContain(`<${name}`);
    }
  });
});

describe("controls line up with what they belong to", () => {
  it("never bottom-aligns a button against a whole field", () => {
    // A Field renders label, input and hint stacked. Putting a Button beside
    // the Field in an items-end row aligns it to the bottom of the hint, so it
    // sits visibly lower than the input it belongs to. Field.action places it
    // in a row with the input instead, where it lines up.
    const offenders: string[] = [];
    for (const file of pageFiles()) {
      const source = read(join(PAGES, file));
      // Look at each flex row that bottom-aligns its children.
      for (const block of source.split("<div").slice(1)) {
        const row = block.slice(0, block.indexOf("</div>"));
        if (!/items-end/.test(row.slice(0, 200))) continue;
        if (/<Field\b/.test(row) && /<Button\b/.test(row)) offenders.push(file);
      }
    }
    expect([...new Set(offenders)]).toEqual([]);
  });

  it("gives Field a way to place a control beside the input", () => {
    const primitives = read(join(SRC, "components/ui/primitives.tsx"));
    expect(primitives).toContain("action?: ReactNode");
  });
});

describe("measured numbers come from one lookup", () => {
  it("never reads model.metrics directly in a page", () => {
    // The built-in model keeps its evaluation on the metrics endpoint, not in
    // model.metrics, so reading that field directly showed "not measured"
    // beside numbers that existed. It happened in the model drawer and then
    // again on the training page, so the lookup belongs in one hook and pages
    // must go through it.
    const offenders: string[] = [];
    for (const file of pageFiles()) {
      const source = read(join(PAGES, file));
      if (/model(\?)?\.metrics/.test(source)) offenders.push(file);
    }
    expect(offenders).toEqual([]);
  });

  it("keeps that lookup in a shared hook", () => {
    const hook = read(join(SRC, "hooks/useModelEvaluation.ts"));
    expect(hook).toContain("api.metrics.overview");
    expect(hook).toContain("held_out_pr_auc");
  });

  it("ships every icon the page asks for", () => {
    // The dashboard declared /brand/spark-mark.png, which was never in
    // web/public. A missing static file is answered by the single page
    // fallback, so the browser received HTML where it expected an image and
    // showed no icon at all. Nothing else catches that: the build succeeds,
    // the types check, and the page renders.
    const html = read(join(SRC, "..", "index.html"));
    const hrefs = [...html.matchAll(/<link[^>]+rel="(?:icon|apple-touch-icon)"[^>]*>/g)]
      .map((tag) => /href="([^"]+)"/.exec(tag[0])?.[1])
      .filter((href): href is string => Boolean(href));

    expect(hrefs.length).toBeGreaterThan(0);

    const missing = hrefs.filter(
      (href) => !existsSync(join(SRC, "..", "public", href.replace(/^\//, "")))
    );
    expect(missing).toEqual([]);
  });

  it("serves the icon browsers request without being told to", () => {
    // A request for /favicon.ico happens whether or not the page declares one.
    expect(existsSync(join(SRC, "..", "public", "favicon.ico"))).toBe(true);
  });
});
