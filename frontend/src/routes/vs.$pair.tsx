import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { api } from "@/lib/api";
import { Comparison } from "@/components/comparison";

export const Route = createFileRoute("/vs/$pair")({
  loader: async ({ params }) => {
    const [sa, sb] = params.pair.split("-vs-");
    if (!sa || !sb) throw notFound();
    const [a, b] = await Promise.all([api.getProduct(sa), api.getProduct(sb)]);
    if (!a || !b) throw notFound();
    return { a, b };
  },
  head: ({ loaderData }) => {
    if (!loaderData) return { meta: [{ title: "Comparison not found — The Beauty Project" }, { name: "robots", content: "noindex" }] };
    const { a, b } = loaderData;
    const t = `${a.brand} ${a.name} vs ${b.brand} ${b.name} | The Beauty Project`;
    const d = `Side-by-side ingredients, price per ml and skin type fit.`;
    return {
      meta: [
        { title: t },
        { name: "description", content: d },
        { property: "og:title", content: t },
        { property: "og:description", content: d },
        { property: "og:type", content: "article" },
        { name: "twitter:card", content: "summary" },
      ],
    };
  },
  notFoundComponent: () => <p className="p-16 text-center">Comparison not found. <Link to="/" className="text-primary">Explore</Link></p>,
  component: VsPage,
});

function VsPage() {
  const { a, b } = Route.useLoaderData();
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-primary">Head to head</p>
        <h1 className="text-2xl font-extrabold tracking-tight">{a.brand} vs {b.brand}</h1>
      </div>
      <Comparison a={a} b={b} aTag={a.brand} bTag={b.brand} />
    </div>
  );
}
