import { DesignPanel } from "./components/DesignPanel";
import { SiteSection } from "./components/SiteSection";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold">Button NZ</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Housing concepts for a real property, designed by an AI agent in
          Blender and checked against the measured site.
        </p>
      </header>
      <div className="grid gap-8 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <SiteSection />
        <DesignPanel />
      </div>
    </main>
  );
}
