"use client";

import { useCallback, useId, useRef, useState } from "react";
import { importSandboxScenario } from "@/lib/api";
import type { SandboxImportResponse } from "@/types/sandbox";

const CLICKWRAP_TEXT =
  "You are configuring a theoretical data simulation. Invest AI will analyze this model. This is not financial advice for your personal assets.";

const ACCEPTED_TYPES = ".csv,.xls,.xlsx";

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export default function SandboxImport() {
  const inputId = useId();
  const checkboxId = useId();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SandboxImportResponse | null>(null);

  const resetFileInput = useCallback(() => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setError(null);
    setResult(null);
  };

  const openModal = () => {
    if (!selectedFile) {
      setError("Choose a CSV or Excel file first.");
      return;
    }
    setAccepted(false);
    setModalOpen(true);
  };

  const closeModal = () => {
    setModalOpen(false);
    setAccepted(false);
  };

  const handleImport = async () => {
    if (!selectedFile || !accepted) return;

    setLoading(true);
    setError(null);
    setModalOpen(false);

    try {
      const data = await importSandboxScenario(selectedFile);
      setResult(data);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "Import failed.");
    } finally {
      setLoading(false);
      setAccepted(false);
    }
  };

  const clearAll = () => {
    setSelectedFile(null);
    setResult(null);
    setError(null);
    resetFileInput();
  };

  return (
    <div className="mx-auto w-full max-w-2xl">
      <header className="mb-8">
        <p className="text-sm font-medium uppercase tracking-wide text-zinc-500">
          Simulated Scenario
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Custom Sandbox
        </h1>
        <p className="mt-3 text-base leading-relaxed text-zinc-600 dark:text-zinc-400">
          Upload a simple holdings file (Symbol, Shares, CostBasis) to model a
          theoretical portfolio. Values are analyzed against a{" "}
          {formatCurrency(100_000)} baseline—not your personal assets.
        </p>
      </header>

      <section className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <label
          htmlFor={inputId}
          className="block text-sm font-medium text-zinc-700 dark:text-zinc-300"
        >
          Scenario file
        </label>
        <input
          ref={fileInputRef}
          id={inputId}
          type="file"
          accept={ACCEPTED_TYPES}
          onChange={handleFileChange}
          className="mt-2 block w-full text-sm text-zinc-600 file:mr-4 file:rounded-lg file:border-0 file:bg-zinc-100 file:px-4 file:py-2 file:text-sm file:font-medium file:text-zinc-800 hover:file:bg-zinc-200 dark:text-zinc-400 dark:file:bg-zinc-800 dark:file:text-zinc-200"
        />
        <p className="mt-2 text-xs text-zinc-500">
          Accepted: CSV, XLS, XLSX. Example columns: Symbol, Shares, CostBasis.
        </p>

        {selectedFile && (
          <p className="mt-3 text-sm text-zinc-700 dark:text-zinc-300">
            Selected:{" "}
            <span className="font-mono font-medium">{selectedFile.name}</span>
          </p>
        )}

        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={openModal}
            disabled={!selectedFile || loading}
            className="rounded-lg bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
          >
            {loading ? "Importing…" : "Import scenario"}
          </button>
          {(selectedFile || result) && (
            <button
              type="button"
              onClick={clearAll}
              disabled={loading}
              className="rounded-lg border border-zinc-300 px-5 py-2.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
            >
              Clear
            </button>
          )}
        </div>

        {error && (
          <p
            role="alert"
            className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200"
          >
            {error}
          </p>
        )}
      </section>

      {result && (
        <section className="mt-8 rounded-xl border border-emerald-200 bg-emerald-50/50 p-6 dark:border-emerald-900/50 dark:bg-emerald-950/20">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
            Scenario loaded
          </h2>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            {result.message}
          </p>
          <p className="mt-3 text-sm font-medium text-zinc-800 dark:text-zinc-200">
            Theoretical baseline:{" "}
            {formatCurrency(result.theoretical_baseline)}
          </p>
          {result.persisted && result.portfolio_name && (
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Saved to {result.portfolio_name}
              {result.user_slug ? ` (${result.user_slug})` : ""}
            </p>
          )}

          <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900">
                  <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
                    Symbol
                  </th>
                  <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
                    Weight
                  </th>
                  <th className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
                    Theoretical $
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.positions.map((pos) => (
                  <tr
                    key={pos.symbol}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                  >
                    <td className="px-4 py-3 font-mono font-medium">
                      {pos.symbol}
                    </td>
                    <td className="px-4 py-3">
                      {pos.weight_pct != null
                        ? `${pos.weight_pct}%`
                        : "—"}
                    </td>
                    <td className="px-4 py-3">
                      {pos.theoretical_value != null
                        ? formatCurrency(pos.theoretical_value)
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="mt-4 text-xs italic leading-relaxed text-zinc-600 dark:text-zinc-400">
            {result.disclaimer}
          </p>
        </section>
      )}

      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="presentation"
          onClick={closeModal}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="clickwrap-title"
            className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl border border-zinc-200 bg-white p-6 shadow-xl dark:border-zinc-700 dark:bg-zinc-950"
            onClick={(e) => e.stopPropagation()}
          >
            <h2
              id="clickwrap-title"
              className="text-lg font-semibold text-zinc-900 dark:text-zinc-50"
            >
              Theoretical simulation agreement
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
              {CLICKWRAP_TEXT}
            </p>
            <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
              File:{" "}
              <span className="font-mono font-medium text-zinc-800 dark:text-zinc-200">
                {selectedFile?.name}
              </span>
            </p>

            <label
              htmlFor={checkboxId}
              className="mt-5 flex cursor-pointer items-start gap-3 rounded-lg border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-900"
            >
              <input
                id={checkboxId}
                type="checkbox"
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-zinc-300"
              />
              <span className="text-sm text-zinc-700 dark:text-zinc-300">
                I understand this is a simulated scenario only and not
                personalized investment advice for my personal assets.
              </span>
            </label>

            <div className="mt-6 flex flex-wrap justify-end gap-3">
              <button
                type="button"
                onClick={closeModal}
                className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-900"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleImport}
                disabled={!accepted}
                className="rounded-lg bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
              >
                Accept &amp; import
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
