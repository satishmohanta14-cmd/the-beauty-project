import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { api } from "@/lib/api";
import { Comparison, DupeRow } from "@/components/comparison";

export const Route = createFileRoute("/dupes/$slug")({
  loader: async ({ params }) => {
    const product = await api.getProduct(params.slug);
    if (!product) throw notFound();
    const dupes = await api.getDupes(params.slug);
    return { product, dupes };
  },
  head: ({ loaderData }) => {
    if (!loaderData) return { meta: [{ title: "Not found — The Beauty Project" }, { name: "robots", content: "noindex" }] };
    const t = `Dupes for ${loaderData.product.brand} ${loaderData.product.name} | The Beauty Project`;
    const d = `Cheaper alternatives ranked by formulation match and price-per-ml savings.`;
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
  notFoundComponent: () => <p className="p-16 text-center">Product not found. <Link to="/" className="text-primary">Explore</Link></p>,
  component: DupesPage,
});

function DupesPage() {
  const { product, dupes } = Route.useLoaderData();
  const top = dupes[0];
  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-primary">Dupe finder</p>
        <h1 className="text-2xl font-extrabold tracking-tight">Alternatives to {product.brand} {product.name}</h1>
      </div>
      {top ? (
        <>
          <Comparison a={product} b={top.product} bTag="Best dupe" />
          <section>
            <h2 className="mb-3 font-bold">All alternatives</h2>
            <div className="space-y-2">
              {dupes.map((d) => <DupeRow key={d.product.slug} base={product} p={d.product} match={d.match} savings={d.savings} />)}
            </div>
          </section>
        </>
      ) : (
        <p className="text-muted-foreground">No alternatives found in this category yet.</p>
      )}
    </div>
  );
}
