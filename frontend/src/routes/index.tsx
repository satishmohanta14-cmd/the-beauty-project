import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { useMemo, useState } from "react";
import { BUDGETS, CATEGORIES, PRODUCTS, SKIN_TYPES } from "@/lib/catalog";
import { inr, lowestOffer } from "@/lib/api";
import { ProductCard } from "@/components/site";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "The Beauty Project — Skincare spec & price comparison" },
      { name: "description", content: "Search serums, sunscreens and moisturizers. Compare actives, INCI lists and lowest prices across Nykaa, Amazon, Tira and Sephora." },
      { property: "og:title", content: "The Beauty Project — Skincare spec & price comparison" },
      { property: "og:description", content: "Compare actives, ingredients and lowest prices across Indian retailers." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Explorer,
});

function Chip({ on, children, onClick }: { on: boolean; children: React.ReactNode; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "shrink-0 rounded-full border px-3 py-1.5 text-xs font-semibold transition",
        on ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-foreground hover:border-primary/50",
      )}
    >
      {children}
    </button>
  );
}

function Explorer() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [focus, setFocus] = useState(false);
  const [cat, setCat] = useState<string | null>(null);
  const [skin, setSkin] = useState<string | null>(null);
  const [budget, setBudget] = useState<number | null>(null);

  const suggestions = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return [];
    return PRODUCTS.filter((p) =>
      [p.brand, p.name, ...p.actives].join(" ").toLowerCase().includes(t),
    ).slice(0, 6);
  }, [q]);

  const results = PRODUCTS.filter(
    (p) =>
      (!cat || p.category === cat) &&
      (!skin || p.skinTypes.includes(skin as never)) &&
      (!budget || lowestOffer(p).price < budget) &&
      (!q || [p.brand, p.name, ...p.actives].join(" ").toLowerCase().includes(q.toLowerCase())),
  );

  return (
    <>
      <section className="bg-hero text-primary-foreground">
        <div className="mx-auto max-w-6xl px-4 py-12 sm:py-16">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary-foreground/60">
            {PRODUCTS.length} products · 4 retailers · live prices
          </p>
          <h1 className="mt-2 max-w-2xl text-3xl font-extrabold tracking-tight sm:text-5xl">
            Know the formula. Pay the lowest price.
          </h1>
          <div className="relative mt-6 max-w-2xl">
            <div className="flex items-center gap-2 rounded-lg bg-card px-4 py-3 text-foreground shadow-lift">
              <Search className="size-5 text-muted-foreground" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onFocus={() => setFocus(true)}
                onBlur={() => setTimeout(() => setFocus(false), 150)}
                placeholder="Search brand, product or active — e.g. Niacinamide"
                className="w-full bg-transparent text-base outline-none placeholder:text-muted-foreground"
              />
            </div>
            {focus && suggestions.length > 0 && (
              <ul className="absolute inset-x-0 top-full z-30 mt-1 overflow-hidden rounded-lg border border-border bg-popover text-popover-foreground shadow-lift">
                {suggestions.map((p) => (
                  <li key={p.slug}>
                    <button
                      onMouseDown={() => navigate({ to: "/p/$slug", params: { slug: p.slug } })}
                      className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm hover:bg-muted"
                    >
                      <span>
                        <span className="font-semibold">{p.brand}</span>{" "}
                        <span className="text-muted-foreground">{p.name}</span>
                      </span>
                      <span className="tabular text-xs font-bold text-success">{inr(lowestOffer(p).price)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      <section className="sticky top-14 z-30 border-b border-border bg-card">
        <div className="mx-auto flex max-w-6xl gap-2 overflow-x-auto px-4 py-3">
          {CATEGORIES.map((c) => (
            <Chip key={c} on={cat === c} onClick={() => setCat(cat === c ? null : c)}>{c}</Chip>
          ))}
          <span className="mx-1 w-px shrink-0 bg-border" />
          {SKIN_TYPES.map((s) => (
            <Chip key={s} on={skin === s} onClick={() => setSkin(skin === s ? null : s)}>{s} skin</Chip>
          ))}
          <span className="mx-1 w-px shrink-0 bg-border" />
          {BUDGETS.map((b) => (
            <Chip key={b.max} on={budget === b.max} onClick={() => setBudget(budget === b.max ? null : b.max)}>{b.label}</Chip>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-6">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-lg font-bold">{results.length} products</h2>
          <span className="text-xs text-muted-foreground">Sorted by relevance</span>
        </div>
        {results.length ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
            {results.map((p) => <ProductCard key={p.slug} p={p} />)}
          </div>
        ) : (
          <p className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">
            No products match these filters.
          </p>
        )}
      </section>
    </>
  );
}
