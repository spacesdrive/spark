/**
 * File dropzone and file preview.
 *
 * Accepts one CSV, because CSV is what the backend can parse safely. It says
 * so up front rather than accepting a spreadsheet and failing later.
 *
 * The browser check here is a courtesy so the user gets an instant answer. The
 * server checks everything again and does not trust any of it.
 */

import { useCallback, useRef, useState } from "react";
import { Icon } from "@/components/ui/icons";
import { Button, Card, CardHeader, ScrollTable, Td, Th } from "@/components/ui/primitives";
import { bytes } from "@/lib/format";
import { cn } from "@/lib/utils";

export function Dropzone({
  onFile,
  maxBytes,
  maxRows,
  busy,
  disabled,
}: {
  onFile: (file: File) => void;
  maxBytes: number;
  maxRows: number;
  busy?: boolean;
  disabled?: boolean;
}) {
  const [over, setOver] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const accept = useCallback(
    (files: FileList | null) => {
      setProblem(null);
      const file = files?.[0];
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".csv")) {
        setProblem(
          "Only CSV files are accepted. Export your data as CSV and try again."
        );
        return;
      }
      if (file.size > maxBytes) {
        setProblem(
          `That file is ${bytes(file.size)}, above the ${bytes(maxBytes)} limit.`
        );
        return;
      }
      onFile(file);
    },
    [maxBytes, onFile]
  );

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          if (!disabled) accept(e.dataTransfer.files);
        }}
        className={cn(
          "rounded-[--radius] border-2 border-dashed px-6 py-10 text-center transition-colors",
          over ? "border-accent bg-accent-soft" : "border-border bg-bg-subtle",
          disabled && "opacity-55"
        )}
        style={{ transitionDuration: "180ms" }}
      >
        <input
          ref={input}
          type="file"
          accept=".csv,text/csv"
          className="sr-only"
          disabled={disabled || busy}
          onChange={(e) => accept(e.target.files)}
        />
        <Icon.Upload size={26} className="mx-auto text-text-faint" />
        <p className="mt-3 text-[14px] font-medium">
          Drop a CSV here, or choose a file
        </p>
        <p className="mx-auto mt-1.5 max-w-md text-[12.5px] leading-relaxed text-text-muted">
          CSV only, UTF-8, up to {bytes(maxBytes)} and {maxRows.toLocaleString()}{" "}
          rows. Excel workbooks and JSON are not supported.
        </p>
        <div className="mt-4">
          <Button
            variant="primary"
            loading={busy}
            disabled={disabled}
            onClick={() => input.current?.click()}
          >
            Choose a file
          </Button>
        </div>
      </div>
      {problem ? (
        <p role="alert" className="mt-2.5 text-[12.5px] text-high">
          {problem}
        </p>
      ) : null}
    </div>
  );
}

export function FilePreview({
  name,
  size,
  rows,
  onRemove,
}: {
  name: string;
  size: number;
  rows: number;
  onRemove?: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-[--radius] border border-border bg-surface px-4 py-3">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-[8px] bg-accent-soft text-accent">
        <Icon.File size={17} />
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-medium">{name}</p>
        <p className="text-[12px] text-text-muted">
          {bytes(size)} · {rows.toLocaleString()} rows
        </p>
      </div>
      {onRemove ? (
        <Button size="sm" variant="ghost" onClick={onRemove} icon={<Icon.Trash size={14} />}>
          Remove
        </Button>
      ) : null}
    </div>
  );
}

/** The first rows, exactly as the server parsed them. */
export function RowPreview({
  columns,
  rows,
  total,
}: {
  columns: string[];
  rows: Record<string, string>[];
  total: number;
}) {
  return (
    <Card>
      <CardHeader
        title="How Spark read your file"
        description={`The first ${rows.length} of ${total.toLocaleString()} rows.
          Check the columns landed where you expect.`}
      />
      <ScrollTable>
        <thead>
          <tr>
            {columns.map((c) => (
              <Th key={c}>{c}</Th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => (
                <Td key={c} className="max-w-[220px] truncate font-mono text-[12px]">
                  {String(row[c] ?? "")}
                </Td>
              ))}
            </tr>
          ))}
        </tbody>
      </ScrollTable>
    </Card>
  );
}
