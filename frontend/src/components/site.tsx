import { Link } from "@tanstack/react-router";
import { ChevronUp, GitCompareArrows, Plus, Check, X, FlaskConical } from "lucide-react";
import { useState } from "react";
import { PRODUCTS, type Product } from "@/lib/catalog";
import { inr, inr2, lowestOffer, perMl } from "@/lib/api";
import { useCompare } from "@/lib/compare";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-card/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <Link to="/" className="flex items-center gap-2 font-extrabold tracking-tight">
          <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
            <FlaskConical className="size-4" />
          </span>
          The Beauty <span className="text-primary">Project</span>
        </Link>
        <nav className="flex items-center gap-4 text-sm font-medium text-muted-foreground">
          <Link to="/" className="hover:text-foreground">Explore</Link>
          <Link to="/dupes/$slug" params={{ slug: "the-ordinary-niacinamide-10" }} className="hover:text-foreground">
            Dupes
          </Link>
          <Link to="/admin" className="hover:text-foreground text-primary font-semibold">
            Admin
          </Link>
        </nav>
      </div>
    </header>
  );
}

export function Packshot({ p, size = "md" }: { p: Product; size?: "sm" | "md" | "lg" }) {
  const h = size === "lg" ? "h-72" : size === "sm" ? "h-16 w-16" : "h-36";
  return (
    <div
      className={cn("relative grid place-items-center overflow-hidden rounded-md border border-border", h)}
      style={{ background: `linear-gradient(160deg, oklch(0.97 0.03 ${p.hue}), oklch(0.9 0.06 ${p.hue}))` }}
    >
      <div
        className={cn("rounded-t-[40%] rounded-b-md shadow-lift", size === "lg" ? "h-48 w-24" : size === "sm" ? "h-10 w-5" : "h-24 w-12")}
        style={{ background: `linear-gradient(90deg, oklch(0.75 0.1 ${p.hue}), oklch(0.88 0.06 ${p.hue}) 45%, oklch(0.7 0.11 ${p.hue}))` }}
      />
      {size !== "sm" && (
        <span className="absolute bottom-2 left-2 text-[10px] font-bold uppercase tracking-widest text-foreground/60">
          {p.brand}
        </span>
      )}
    </div>
  );
}

export function CompareButton({ slug, className }: { slug: string; className?: string }) {
  const { has, toggle, items } = useCompare();
  const on = has(slug);
  return (
    <Button
      size="sm"
      variant={on ? "default" : "outline"}
      disabled={!on && items.length >= 4}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggle(slug);
      }}
      className={className}
    >
      {on ? <Check /> : <Plus />} {on ? "Added" : "Compare"}
    </Button>
  );
}

export function ProductCard({ p }: { p: Product }) {
  const o = lowestOffer(p);
  return (
    <Link
      to="/p/$slug"
      params={{ slug: p.slug }}
      className="group flex flex-col rounded-lg border border-border bg-card p-3 shadow-card transition hover:-translate-y-0.5 hover:shadow-lift"
    >
      <Packshot p={p} />
      <div className="mt-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{p.brand}</div>
      <div className="mt-0.5 line-clamp-2 min-h-10 text-sm font-bold leading-snug">{p.name}</div>
      <div className="mt-2 flex flex-wrap gap-1">
        {p.actives.slice(0, 2).map((a) => (
          <Badge key={a} variant="info" className="text-[10px]">{a}</Badge>
        ))}
      </div>
      <div className="mt-auto flex items-end justify-between pt-3">
        <div>
          <Badge variant="success" className="text-[10px]">Lowest · {o.retailer}</Badge>
          <div className="tabular mt-1 text-lg font-bold">{inr(o.price)}</div>
          <div className="tabular text-[11px] text-muted-foreground">{inr2(perMl(o))}/ml</div>
        </div>
        <CompareButton slug={p.slug} />
      </div>
    </Link>
  );
}

export function CompareDrawer() {
  const { items, remove, clear } = useCompare();
  const [open, setOpen] = useState(false);
  const products = items.map((s) => PRODUCTS.find((p) => p.slug === s)!).filter(Boolean);
  if (products.length === 0) return null;
  const ready = products.length >= 2;
  return (
    <div className="fixed inset-x-0 bottom-0 z-50 animate-in slide-in-from-bottom duration-300">
      <div className="mx-auto max-w-6xl px-2 sm:px-4">
        <div className="rounded-t-xl border border-b-0 border-border bg-card shadow-lift">
          <div className="flex items-center gap-3 p-3">
            <button onClick={() => setOpen(!open)} className="flex items-center gap-2 text-sm font-bold" disabled={!ready}>
              <GitCompareArrows className="size-4 text-primary" />
              Compare ({products.length}/4)
              {ready && <ChevronUp className={cn("size-4 transition", open && "rotate-180")} />}
            </button>
            <div className="flex flex-1 gap-2 overflow-x-auto">
              {products.map((p) => (
                <span key={p.slug} className="flex shrink-0 items-center gap-1 rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-medium">
                  {p.brand}
                  <button onClick={() => remove(p.slug)} aria-label={`Remove ${p.name}`}><X className="size-3" /></button>
                </span>
              ))}
            </div>
            <Button variant="ghost" size="sm" onClick={clear}>Clear</Button>
            {ready ? (
              <Button size="sm" asChild>
                <Link to="/vs/$pair" params={{ pair: `${products[0]!.slug}-vs-${products[1]!.slug}` }}>Compare now</Link>
              </Button>
            ) : (
              <span className="hidden text-xs text-muted-foreground sm:inline">Add 1 more</span>
            )}
          </div>
          {open && ready && (
            <div className="max-h-[50vh] overflow-auto border-t border-border">
              <table className="w-full text-sm">
                <tbody>
                  {[
                    ["Product", (p: Product) => <span className="font-bold">{p.name}</span>],
                    ["Lowest price", (p: Product) => <span className="tabular font-bold text-success">{inr(lowestOffer(p).price)}</span>],
                    ["Price / ml", (p: Product) => <span className="tabular">{inr2(perMl(lowestOffer(p)))}</span>],
                    ["Actives", (p: Product) => p.actives.join(", ")],
                    ["Skin type", (p: Product) => p.skinTypes.join(", ")],
                    ["DCS", (p: Product) => <span className="tabular">{p.dcs}/100</span>],
                  ].map(([label, fn]) => (
                    <tr key={label as string} className="border-b border-border last:border-0">
                      <th className="w-28 bg-muted px-3 py-2 text-left text-xs font-semibold text-muted-foreground">{label as string}</th>
                      {products.map((p) => (
                        <td key={p.slug} className="min-w-40 px-3 py-2 align-top">{(fn as (p: Product) => React.ReactNode)(p)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
