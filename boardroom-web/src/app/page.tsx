import SandboxImport from "@/components/SandboxImport";

export default function Home() {
  return (
    <div className="min-h-full bg-zinc-50 dark:bg-black">
      <main className="mx-auto flex min-h-full max-w-3xl flex-col px-6 py-16 sm:px-10">
        <SandboxImport />
      </main>
      <footer className="border-t border-zinc-200 px-6 py-6 text-center text-xs text-zinc-500 dark:border-zinc-800">
        Invest AI Boardroom — informational simulation only; not investment
        advice.
      </footer>
    </div>
  );
}
