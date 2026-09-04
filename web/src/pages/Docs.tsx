/**
 * Documentation, written for someone who has never done machine learning.
 *
 * Every technical word is explained the moment it is used. No sentence here
 * needs a glossary to get through.
 */

import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAsync } from "@/hooks/useAsync";
import { Icon } from "@/components/ui/icons";
import { PinnedList } from "@/components/ui/PinnedList";
import {
  Badge,
  Callout,
  Card,
  CardHeader,
  PageHeader,
  ScrollTable,
  Section,
  Td,
  Th,
} from "@/components/ui/primitives";

const GLOSSARY: [string, string][] = [
  ["Feature", "A single piece of information given to the model, such as the amount, or how many payments this customer made in the last hour."],
  ["Model", "A program that has learned patterns from past data and uses them to score something new."],
  ["Training", "Showing a model lots of past examples so it can learn the patterns."],
  ["Label", "What actually happened afterwards. Here, 1 means fraud and 0 means normal."],
  ["Precision", "Out of everything the model flagged, how much was really fraud. Higher means fewer annoyed real customers."],
  ["Recall", "Out of all the fraud there was, how much the model caught. Higher means less money lost."],
  ["F1", "One number that balances precision and recall, so you can compare two setups at a glance."],
  ["PR-AUC", "How well the model sorts fraud above normal traffic when fraud is rare. Runs from 0 to 1, higher is better."],
  ["ROC-AUC", "How well the model separates fraud from normal overall. Easier to score well on than PR-AUC."],
  ["False positive", "A normal transaction the model wrongly flagged. It costs you the sale and annoys the customer."],
  ["False negative", "Real fraud the model missed. It costs you the money."],
  ["Threshold", "The cut-off score above which Spark acts. Move it up and you flag less; move it down and you flag more."],
  ["Calibration", "Adjusting the scores so that a 0.8 really does mean about an 80 in 100 chance, rather than just being higher than 0.7."],
  ["Held-out test", "A slice of data set aside and looked at only once, at the very end. It is the only honest estimate of how the model behaves on data it has never seen."],
  ["Graph", "A picture of what is connected to what. Here, transactions are connected when they share a customer, a merchant, a location or a payment channel."],
  ["Abuse ring", "A group of accounts working together. Each payment looks fine alone; the pattern only shows up when you look at the group."],
  ["PSI", "A number saying how much a distribution has moved between two periods. Below 0.10 is stable, above 0.25 means it really moved."],
  ["Chargeback", "When a customer disputes a payment and the money is taken back. It usually arrives weeks after the payment."],
];

const SECTIONS = [
  { id: "start", label: "Getting started", hint: "What Spark is and how it decides" },
  { id: "testing", label: "Testing", hint: "One transaction, or a whole file" },
  { id: "data", label: "Your data", hint: "Columns, formats and limits" },
  { id: "results", label: "Understanding results", hint: "What each number means" },
  { id: "models", label: "Models", hint: "Built in, custom and production" },
  { id: "security", label: "Security and privacy", hint: "What is stored and who can read it" },
  { id: "glossary", label: "Glossary", hint: "Plain definitions of the terms" },
];

/** The icon shown beside a section in the pinned list. */
const SECTION_ICON: Record<string, keyof typeof Icon> = {
  start: "Home",
  testing: "Transaction",
  data: "Dataset",
  results: "Chart",
  models: "Model",
  security: "Key",
  glossary: "Book",
};

export function Docs() {
  const [section, setSection] = useState("start");
  const format = useAsync(() => api.datasets.format(), []);
  const config = useAsync(() => api.config(), []);

  return (
    <div className="space-y-6">
      <PageHeader
        breadcrumb={[{ label: "More" }, { label: "Documentation" }]}
        title="Documentation"
        description="How to use Spark, written for someone who knows computers but
          has never done machine learning."
        action={
          config.data?.docs_url ? (
            <a href={config.data.docs_url} target="_blank" rel="noreferrer">
              <span className="interactive inline-flex h-9 items-center gap-2 rounded-[8px] border border-border bg-surface px-3 text-[13px]">
                <Icon.Book size={15} />
                Full documentation site
              </span>
            </a>
          ) : null
        }
      />

      <Section
        title="Sections"
        description="Pin the ones you come back to and they stay at the top."
      >
        <PinnedList
          storageKey="spark.docs.pinned"
          items={SECTIONS.map((s) => {
            const Glyph = Icon[SECTION_ICON[s.id] ?? "Book"];
            return {
              id: s.id,
              name: s.label,
              subtitle: s.hint,
              icon: <Glyph size={16} />,
              onOpen: () => setSection(s.id),
            };
          })}
        />
      </Section>

      {section === "start" ? (
        <div className="space-y-3">
          <Card>
            <CardHeader title="What is Spark" />
            <div className="space-y-3 px-5 py-4 text-[13.5px] leading-relaxed text-text-muted">
              <p>
                Spark looks at payment transactions and does two things. It gives
                each one a risk score and decides whether to approve it, send it to
                a person, or block it. Separately, it finds groups of accounts that
                look like they are working together.
              </p>
              <p>
                The second part is the interesting one. A single suspicious payment
                is easy to spot. A fraud ring is harder: many fake accounts spending
                small amounts through the same merchant and channel. Each payment
                alone looks fine, and the pattern only appears when you look at the
                group.
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader title="Try it in three minutes" />
            <ol className="divide-y divide-border">
              {[
                ["Score one transaction", "Go to Test Transaction, press one of the examples, and press Score. You will get a risk score, a decision, and a list of what moved the score.", "/transaction"],
                ["Upload some of your own data", "Go to Test Dataset and drop in a CSV. Spark checks the columns, scores every row, and lets you download the results.", "/dataset"],
                ["See what was measured", "Go to Risk Analysis for the full evaluation, including the parts that did not work.", "/analysis"],
              ].map(([title, detail, href], i) => (
                <li key={title} className="flex items-start gap-3 px-5 py-3.5">
                  <span
                    aria-hidden="true"
                    className="flex size-5 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent"
                  >
                    {i + 1}
                  </span>
                  <div>
                    <Link to={href} className="text-[13px] font-medium text-link hover:underline">
                      {title}
                    </Link>
                    <p className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                      {detail}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          <Card>
            <CardHeader title="Do I need an account" />
            <div className="px-5 py-4 text-[13.5px] leading-relaxed text-text-muted">
              <p>
                Not for anything above. An account is only needed to train a model
                on your own data, keep private models, and create API keys. Those
                create things that belong to you alone, so the server has to know
                who you are.
              </p>
            </div>
          </Card>
        </div>
      ) : null}

      {section === "testing" ? (
        <div className="space-y-3">
          <Card>
            <CardHeader
              title="Three different things, kept separate"
              description="Confusing these is the easiest way to fool yourself."
            />
            <ScrollTable>
              <thead>
                <tr>
                  <Th>What</Th>
                  <Th>Data used</Th>
                  <Th>What it tells you</Th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <Td className="font-medium">Spark Example Test Data</Td>
                  <Td>The dataset Spark was built on</Td>
                  <Td className="text-text-muted">
                    How Spark itself works. It does not tell you how Spark would do
                    on your business.
                  </Td>
                </tr>
                <tr>
                  <Td className="font-medium">Your test data</Td>
                  <Td>A CSV you upload</Td>
                  <Td className="text-text-muted">
                    How the existing model behaves on your transactions. With labels,
                    it also measures how accurate it was.
                  </Td>
                </tr>
                <tr>
                  <Td className="font-medium">Your training data</Td>
                  <Td>A CSV you upload, marked as training</Td>
                  <Td className="text-text-muted">
                    Used to build a model of your own. Never mixed with test data.
                  </Td>
                </tr>
              </tbody>
            </ScrollTable>
            <div className="px-5 py-4">
              <Callout tone="warning" title="Spark never trains on your test data">
                Test uploads and training uploads are stored separately and marked
                separately. Training on something you uploaded for testing would
                mean measuring a model on data it had already seen, which produces
                a flattering number that means nothing.
              </Callout>
            </div>
          </Card>
        </div>
      ) : null}

      {section === "data" && format.data ? (
        <div className="space-y-3">
          <Card>
            <CardHeader
              title="Preparing your data"
              description="Your dataset is a table. Each row is one transaction."
            />
            <ScrollTable>
              <thead>
                <tr>
                  <Th>Column</Th>
                  <Th>Needed</Th>
                  <Th>Why</Th>
                  <Th>Also accepted as</Th>
                </tr>
              </thead>
              <tbody>
                {format.data.columns.map((c) => (
                  <tr key={c.column}>
                    <Td className="font-medium">{c.label}</Td>
                    <Td>
                      <Badge
                        tone={
                          c.requirement === "required"
                            ? "high"
                            : c.requirement === "recommended"
                              ? "medium"
                              : "neutral"
                        }
                      >
                        {c.requirement}
                      </Badge>
                    </Td>
                    <Td className="max-w-md text-text-muted">{c.why}</Td>
                    <Td className="font-mono text-[11.5px] text-text-faint">
                      {c.accepted_names.join(", ")}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </ScrollTable>
          </Card>

          <Card>
            <CardHeader title="An example file" />
            <pre className="overflow-x-auto px-5 py-4 font-mono text-[11.5px] leading-relaxed">
              {format.data.example_csv}
            </pre>
          </Card>

          <Card>
            <CardHeader
              title="Labels"
              description="A label says what actually happened after the
                transaction."
            />
            <ScrollTable>
              <thead>
                <tr>
                  <Th>Value</Th>
                  <Th>Meaning</Th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(format.data.label_meaning).map(([value, meaning]) => (
                  <tr key={value}>
                    <Td className="font-mono">{value}</Td>
                    <Td className="text-text-muted">{meaning}</Td>
                  </tr>
                ))}
              </tbody>
            </ScrollTable>
            <div className="px-5 py-4">
              <Callout tone="info">
                You only need labels if you want accuracy measured. Without them
                Spark scores every row perfectly happily; it just cannot tell you
                how many of those scores were right.
              </Callout>
            </div>
          </Card>

          <Card>
            <CardHeader title="Things worth knowing" />
            <ul className="divide-y divide-border">
              {format.data.notes.map((n) => (
                <li key={n} className="flex items-start gap-2.5 px-5 py-3">
                  <Icon.Info size={14} className="mt-0.5 shrink-0 text-text-faint" />
                  <span className="text-[13px] leading-relaxed text-text-muted">{n}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      ) : null}

      {section === "results" ? (
        <div className="space-y-3">
          <Card>
            <CardHeader title="Reading a risk result" />
            <div className="space-y-3 px-5 py-4 text-[13.5px] leading-relaxed text-text-muted">
              <p>
                <strong className="text-text">The risk score</strong> is a number
                between 0 and 1. It is calibrated, which means it is meant to track
                the real chance of fraud rather than just being a ranking.
              </p>
              <p>
                <strong className="text-text">The decision</strong> comes from two
                cut-off points. Below the first, approve. Between the two, send to a
                person. Above the second, block. Both cut-offs were chosen by
                working out which ones cost the least money, on data separate from
                the final test.
              </p>
              <p>
                <strong className="text-text">The explanation</strong> lists the
                features that moved the score most. These contributed to the score.
                They are not proof that anything is fraud, and Spark is careful to
                word it that way, because someone whose payment was declined may
                well challenge it.
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Why accuracy alone is not enough"
              description="A fraud system is only worth running if the money
                improves."
            />
            <div className="space-y-3 px-5 py-4 text-[13.5px] leading-relaxed text-text-muted">
              <p>
                Blocking a real customer costs you the sale and their goodwill.
                Missing real fraud costs you the money. Those are not the same size,
                and they are not the same size as each other for a 5 payment and a
                5,000 payment.
              </p>
              <p>
                So Spark prices them: 25 for wrongly blocking a good order, the full
                amount plus 15 for missing fraud, and 3 for each human review, where
                a review only catches 80 out of 100 of the fraud sent to it.
                Thresholds are then picked to make the total as small as possible,
                not to make any single metric look good.
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="What Spark does not do well"
              description="Stated here rather than buried."
            />
            <ul className="divide-y divide-border">
              {[
                ["It was trained on simulated data", "The results describe that file, not the payments industry. The method and the way it is tested are what carry over."],
                ["Its calibration drifts", "The score distribution moved a lot between the validation window and the test window. In real use you would recalibrate regularly."],
                ["One threshold setting does not transfer", "The high precision setting was chosen correctly, then almost nothing in the later window reached it. Spark reports that as a failure."],
                ["New merchants are harder", "Accuracy drops noticeably on entities Spark had barely seen. History features cannot help where there is no history."],
                ["No device or IP data", "Two of the strongest signals in real fraud work are missing from the source data, and Spark does not invent them."],
              ].map(([title, detail]) => (
                <li key={title} className="flex items-start gap-3 px-5 py-3.5">
                  <Icon.Alert size={15} className="mt-0.5 shrink-0 text-medium" />
                  <div>
                    <p className="text-[13px] font-medium">{title}</p>
                    <p className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                      {detail}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      ) : null}

      {section === "models" ? (
        <div className="space-y-3">
          <Card>
            <CardHeader title="Hybrid V1" description="The model Spark ships with." />
            <div className="space-y-3 px-5 py-4 text-[13.5px] leading-relaxed text-text-muted">
              <p>
                Hybrid V1 runs four separate scores and blends them into one.
              </p>
              <ul className="space-y-2 pl-4">
                <li>
                  <strong className="text-text">The tree model</strong> looks at
                  amounts, counts and history. It is fast, it handles a lot of
                  features without much tuning, and it can explain itself precisely.
                </li>
                <li>
                  <strong className="text-text">The graph model</strong> mixes each
                  transaction with the transactions it shares a customer, merchant,
                  location or channel with. It only ever looks backwards in time.
                </li>
                <li>
                  <strong className="text-text">The behaviour score</strong> asks how
                  unusual this is for this account.
                </li>
                <li>
                  <strong className="text-text">The velocity score</strong> asks how
                  fast and how concentrated the recent activity is.
                </li>
              </ul>
              <p>
                The last two read no fraud labels at all, which is why they keep
                working when chargebacks are slow to arrive.
              </p>
              <p>
                How much each one counts was found by trying 400 combinations on
                validation data and keeping the best. It was not picked by hand.
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader
              title="The rule that matters most"
              description="A transaction only ever sees the past."
            />
            <div className="space-y-3 px-5 py-4 text-[13.5px] leading-relaxed text-text-muted">
              <p>
                Features for transaction 10 are built from transactions 0 to 9 and
                nothing later. Graph links point only from older to newer. And a
                confirmed outcome does not become usable the instant it happens,
                because in real life a chargeback arrives weeks after the payment.
              </p>
              <p>
                If you break any of these, the numbers look wonderful and mean
                nothing, because the model has been shown the answer. Three separate
                tests check that it holds.
              </p>
            </div>
          </Card>
        </div>
      ) : null}

      {section === "security" ? (
        <div className="space-y-3">
          <Card>
            <CardHeader title="What happens to a file you upload" />
            <ul className="divide-y divide-border">
              {[
                ["It is never executed", "It is read as text and parsed as CSV. Nothing in it runs, and no Python object is ever loaded from it."],
                ["It is stored under a random name", "Not the name you gave it. Your filename is only kept for display."],
                ["It is deleted", "Uploads are removed after the retention window shown on the training page, and you can delete one immediately from the dataset page."],
                ["Downloads are made safe", "Values that a spreadsheet would run as a formula are prefixed, so opening the results file cannot execute anything."],
                ["It belongs to you", "A file uploaded under an organization is visible only to members of that organization. The server checks that on every request."],
              ].map(([title, detail]) => (
                <li key={title} className="flex items-start gap-3 px-5 py-3.5">
                  <Icon.CheckCircle size={15} className="mt-0.5 shrink-0 text-low" />
                  <div>
                    <p className="text-[13px] font-medium">{title}</p>
                    <p className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                      {detail}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Signing in" />
            <div className="space-y-3 px-5 py-4 text-[13.5px] leading-relaxed text-text-muted">
              <p>
                Google sign-in runs through Supabase. The token it produces is sent
                to Spark once, checked, and swapped for a session cookie your
                browser cannot read from a script. No long-lived token sits in
                browser storage.
              </p>
              <p>
                Signing out ends the session on the server, not just in your tab.
                Sessions also expire on their own.
              </p>
            </div>
          </Card>

          <Card>
            <CardHeader title="What the dashboard never shows" />
            <ul className="grid gap-2 px-5 py-4 text-[13px] text-text-muted sm:grid-cols-2">
              {[
                "Server file paths",
                "Stack traces",
                "Any private credential",
                "Another organization's data",
                "An API key after it was created",
                "Database or cloud secrets",
              ].map((item) => (
                <li key={item} className="flex items-center gap-2">
                  <Icon.Block size={14} className="shrink-0 text-text-faint" />
                  {item}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      ) : null}

      {section === "glossary" ? (
        <Card>
          <CardHeader
            title="Glossary"
            description="Every technical word this dashboard uses."
          />
          <dl className="divide-y divide-border">
            {GLOSSARY.map(([term, meaning]) => (
              <div key={term} className="px-5 py-3">
                <dt className="text-[13px] font-semibold">{term}</dt>
                <dd className="mt-0.5 text-[12.5px] leading-relaxed text-text-muted">
                  {meaning}
                </dd>
              </div>
            ))}
          </dl>
        </Card>
      ) : null}
    </div>
  );
}
