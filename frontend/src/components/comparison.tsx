import { Link } from "@tanstack/react-router";
import { ArrowRight } from "lucide-react";
import type { Product } from "@/lib/catalog";
import { SKIN_TYPES } from "@/lib/catalog";
import { inr, inr2, lowestOffer, perMl, similarity } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Packshot } from "@/components/site";
import { cn } from "@/lib/utils";

function Gauge({ value, label, tone }: { value: number; label: string; tone: "primary" | "success" }) {
  const v = Math.max(0, Math.min(100, value));
  const c = 2 * Math.PI * 42;
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 100 100" className="size-28 -rotate-90">
        <circle cx="50" cy="50" r="42" fill="none" stroke="var(--border)" strokeWidth="9" />
        <circle
          cx="50" cy="50" r="42" fill="none"
          stroke={tone === "primary" ? "var(--primary)" : "var(--success)"}
          strokeWidth="9" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v / 100)}
          className="transition-all duration-700"
        />
      </svg>
      <div className="tabular -mt-[4.6rem] mb-10 text-2xl font-bold">{value}%</div>
      <div className="text-xs font-semibold text-muted-foreground">{label}</div>
    </div>
  );
}

function Side({ p, tag }: { p: Product; tag: string }) {
  const o = lowestOffer(p);
  return (
    <Card className="flex-1">
      <CardContent className="p-4">
        <Badge variant={tag === "Original" ? "pill" : "success-soft"}>{tag}</Badge>
        <div className="mt-3"><Packshot p={p} /></div>
        <div className="mt-3 text-xs font-bold uppercase tracking-wide text-muted-foreground">{p.brand}</div>
        <Link to="/p/$slug" params={{ slug: p.slug }} className="font-bold hover:text-primary">{p.name}</Link>
        <div className="tabular mt-2 text-xl font-bold">{inr(o.price)}</div>
        <div className="tabular text-xs text-muted-foreground">{inr2(perMl(o))}/ml at {o.retailer}</div>
      </CardContent>
    </Card>
  );
}

export function Comparison({ a, b, aTag = "Original", bTag = "Alternative" }: { a: Product; b: Product; aTag?: string; bTag?: string }) {
  const s = similarity(a, b);
  const fit = (p: Product, t: string) => (p.skinTypes.includes(t as never) ? 5 : 2);
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-stretch">
        <Side p={a} tag={aTag} />
        <Card className="md:w-64">
          <CardContent className="flex h-full flex-row items-center justify-around gap-2 p-4 md:flex-col">
            <Gauge value={s.match} label="Formulation match" tone="primary" />
            <Gauge value={Math.abs(s.savings)} label={s.savings >= 0 ? "Price savings / ml" : "Costlier / ml"} tone="success" />
          </CardContent>
        </Card>
        <Side p={b} tag={bTag} />
      </div>

      <Card>
        <CardContent className="px-0 py-2">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Spec</TableHead>
                <TableHead>{a.brand}</TableHead>
                <TableHead className="pr-6">{b.brand}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell className="pl-6 font-semibold">Price / ml</TableCell>
                {[a, b].map((p) => {
                  const cheaper = perMl(lowestOffer(p)) <= Math.min(perMl(lowestOffer(a)), perMl(lowestOffer(b)));
                  return (
                    <TableCell key={p.slug} className={cn("tabular font-bold", cheaper && "text-success")}>
                      {inr2(perMl(lowestOffer(p)))}
                    </TableCell>
                  );
                })}
              </TableRow>
              <TableRow>
                <TableCell className="pl-6 font-semibold">Shared ingredients</TableCell>
                <TableCell colSpan={2} className="pr-6">
                  <div className="flex flex-wrap gap-1">
                    {s.shared.map((x) => <Badge key={x} variant="success-soft">{x}</Badge>)}
                  </div>
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell className="pl-6 font-semibold">Unique ingredients</TableCell>
                {[s.uniqueA, s.uniqueB].map((list, i) => (
                  <TableCell key={i} className="align-top">
                    <div className="flex flex-wrap gap-1">
                      {list.length ? list.map((x) => <Badge key={x} variant="pill">{x}</Badge>) : <span className="text-muted-foreground">—</span>}
                    </div>
                  </TableCell>
                ))}
              </TableRow>
              <TableRow>
                <TableCell className="pl-6 font-semibold">Key actives</TableCell>
                {[a, b].map((p) => <TableCell key={p.slug}>{p.actives.join(", ")}</TableCell>)}
              </TableRow>
              {SKIN_TYPES.map((t) => (
                <TableRow key={t}>
                  <TableCell className="pl-6 font-semibold">{t} skin fit</TableCell>
                  {[a, b].map((p) => (
                    <TableCell key={p.slug}>
                      <div className="flex gap-0.5">
                        {Array.from({ length: 5 }, (_, i) => (
                          <span key={i} className={cn("h-1.5 w-5 rounded-full", i < fit(p, t) ? "bg-success" : "bg-border")} />
                        ))}
                      </div>
                    </TableCell>
                  ))}
                </TableRow>
              ))}
              <TableRow>
                <TableCell className="pl-6 font-semibold">Data completeness</TableCell>
                {[a, b].map((p) => <TableCell key={p.slug} className="tabular">{p.dcs}/100</TableCell>)}
              </TableRow>
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

export function DupeRow({ base, p, match, savings }: { base: Product; p: Product; match: number; savings: number }) {
  return (
    <Link
      to="/vs/$pair"
      params={{ pair: `${base.slug}-vs-${p.slug}` }}
      className="flex items-center gap-3 rounded-lg border border-border bg-card p-3 shadow-card transition hover:border-primary/40"
    >
      <Packshot p={p} size="sm" />
      <div className="min-w-0 flex-1">
        <div className="text-xs font-bold uppercase text-muted-foreground">{p.brand}</div>
        <div className="truncate text-sm font-semibold">{p.name}</div>
      </div>
      <Badge variant="info" className="tabular">{match}% match</Badge>
      {savings > 0 && <Badge variant="success" className="tabular hidden sm:inline-flex">Save {savings}%</Badge>}
      <ArrowRight className="size-4 text-muted-foreground" />
    </Link>
  );
}
