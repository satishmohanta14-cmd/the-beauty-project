import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { ArrowUpRight, BadgeCheck, Copy, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, inr, inr2, lowestOffer, perMl, priceHistory } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CompareButton, Packshot } from "@/components/site";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/p/$slug")({
  loader: async ({ params }) => {
    const product = await api.getProduct(params.slug);
    if (!product) throw notFound();
    const ingredients = await api.getIngredients(params.slug);
    return { product, ingredients };
  },
  head: ({ loaderData }) => {
    if (!loaderData) return { meta: [{ title: "Product not found — The Beauty Project" }, { name: "robots", content: "noindex" }] };
    const p = loaderData.product;
    const t = `${p.brand} ${p.name} — Price, Ingredients & Specs | The Beauty Project`;
    const d = `Lowest price ${inr(lowestOffer(p).price)}. Compare ${p.offers.length} retailers, INCI list and price history.`;
    return {
      meta: [
        { title: t },
        { name: "description", content: d },
        { property: "og:title", content: t },
        { property: "og:description", content: d },
        { property: "og:type", content: "product" },
        { name: "twitter:card", content: "summary" },
      ],
    };
  },
  notFoundComponent: () => (
    <div className="mx-auto max-w-md p-16 text-center">
      <h1 className="text-xl font-bold">Product not found</h1>
      <Link to="/" className="mt-4 inline-block text-primary">Back to explorer</Link>
    </div>
  ),
  component: ProductPage,
});

const comedoColor = (n: number) => (n <= 1 ? "text-success" : n <= 3 ? "text-chart-5" : "text-destructive");
const safetyVariant = (s: string) => (s === "A" ? "success-soft" : s === "B" ? "pill" : "destructive") as never;

function ProductPage() {
  const { product: p, ingredients } = Route.useLoaderData();
  const [size, setSize] = useState(p.sizes[0]);
  const best = lowestOffer(p);
  const offers = [...p.offers].sort((a, b) => perMl(a) - perMl(b));
  const history = priceHistory(p);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6">
      <nav className="text-xs text-muted-foreground">
        <Link to="/" className="hover:text-foreground">Explore</Link> / {p.category} / <span className="text-foreground">{p.brand}</span>
      </nav>

      <section className="grid gap-6 rounded-lg border border-border bg-card p-4 shadow-card md:grid-cols-[320px_1fr] md:p-6">
        <Packshot p={p} size="lg" />
        <div className="flex flex-col">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">{p.brand}</span>
            <Badge variant="info" className="tabular">DCS: {p.dcs}/100</Badge>
          </div>
          <h1 className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">{p.name}</h1>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {p.actives.map((a) => <Badge key={a} variant="info">{a}</Badge>)}
          </div>
          <div className="mt-4">
            <div className="text-xs font-semibold text-muted-foreground">Size</div>
            <div className="mt-1.5 flex gap-2">
              {p.sizes.map((s) => (
                <button
                  key={s}
                  onClick={() => setSize(s)}
                  className={cn(
                    "rounded-full border px-4 py-1.5 text-sm font-semibold tabular",
                    size === s ? "border-primary bg-accent text-accent-foreground" : "border-border",
                  )}
                >
                  {s}ml
                </button>
              ))}
            </div>
          </div>
          <ul className="mt-4 grid gap-1.5 text-sm sm:grid-cols-2">
            {p.claims.map((c) => (
              <li key={c} className="flex items-center gap-2"><BadgeCheck className="size-4 text-success" />{c}</li>
            ))}
          </ul>
          <div className="mt-auto flex flex-wrap items-end justify-between gap-3 border-t border-border pt-4">
            <div>
              <Badge variant="success">Lowest price · {best.retailer}</Badge>
              <div className="tabular mt-1 text-3xl font-bold">{inr(best.price)}</div>
              <div className="tabular text-xs text-muted-foreground">{inr2(perMl(best))}/ml · {best.ml}ml</div>
            </div>
            <div className="flex gap-2">
              <CompareButton slug={p.slug} />
              <Button variant="outline" size="sm" asChild>
                <Link to="/dupes/$slug" params={{ slug: p.slug }}><Copy /> Find dupes</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>

      <Card>
        <CardHeader><CardTitle className="text-base">Live retailer prices</CardTitle></CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Store</TableHead>
                <TableHead>Size</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Price/ml</TableHead>
                <TableHead className="pr-6 text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {offers.map((o) => (
                <TableRow key={o.id} className={cn(!o.inStock && "opacity-50")}>
                  <TableCell className="pl-6">
                    <div className="flex items-center gap-2">
                      <span className="grid size-8 place-items-center rounded-md border border-border bg-muted text-xs font-extrabold">{o.retailer[0]}</span>
                      <div>
                        <div className="font-semibold">{o.retailer}</div>
                        {o.id === best.id && <Badge variant="success" className="text-[10px]">Lowest</Badge>}
                        {!o.inStock && <span className="text-[11px] text-destructive">Out of stock</span>}
                        {o.inStock && o.id !== best.id && <span className="text-[11px] text-success">In stock</span>}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="tabular">{o.ml}ml</TableCell>
                  <TableCell className="tabular text-right font-bold">{inr(o.price)}</TableCell>
                  <TableCell className="tabular hidden text-right text-muted-foreground sm:table-cell">{inr2(perMl(o))}</TableCell>
                  <TableCell className="pr-6 text-right">
                    <Button size="sm" disabled={!o.inStock} asChild={o.inStock}>
                      {o.inStock ? (
                        <a href={`/go/${o.id}`} target="_blank" rel="noopener noreferrer">View Deal <ArrowUpRight /></a>
                      ) : (
                        <span>Unavailable</span>
                      )}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">30-day price history</CardTitle></CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={history} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} interval={5} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickFormatter={(v) => "₹" + v} width={60} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
                <Tooltip formatter={(v: number) => inr(v)} contentStyle={{ borderRadius: 8, border: "1px solid var(--border)", fontSize: 12 }} />
                <Line type="monotone" dataKey="price" stroke="var(--primary)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-base">INCI ingredients</CardTitle>
          <span className="flex items-center gap-1 text-xs text-muted-foreground"><ShieldCheck className="size-3.5" /> Ordered by concentration</span>
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10 pl-6">#</TableHead>
                <TableHead>Ingredient</TableHead>
                <TableHead className="hidden sm:table-cell">Function</TableHead>
                <TableHead className="text-center">Comedogenic</TableHead>
                <TableHead className="pr-6 text-center">Safety</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {ingredients.map((i, idx) => (
                <TableRow key={i.name}>
                  <TableCell className="tabular pl-6 text-muted-foreground">{idx + 1}</TableCell>
                  <TableCell>
                    <div className="font-semibold">{i.name}</div>
                    <div className="text-xs text-muted-foreground sm:hidden">{i.fn}</div>
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground sm:table-cell">{i.fn}</TableCell>
                  <TableCell className={cn("tabular text-center font-bold", comedoColor(i.comedogenic))}>{i.comedogenic}/5</TableCell>
                  <TableCell className="pr-6 text-center"><Badge variant={safetyVariant(i.safety)}>{i.safety}</Badge></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
