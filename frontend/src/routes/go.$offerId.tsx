import { createFileRoute, redirect } from "@tanstack/react-router";
import { api } from "@/lib/api";

// GET /go/:offerId — resolves an offer and redirects to the retailer.
export const Route = createFileRoute("/go/$offerId")({
  loader: async ({ params }) => {
    const offer = await api.resolveOffer(params.offerId);
    if (!offer) throw redirect({ to: "/" });
    throw redirect({ href: offer.url });
  },
  head: () => ({ meta: [{ title: "Redirecting to retailer…" }, { name: "robots", content: "noindex" }] }),
  component: () => <p className="p-16 text-center text-muted-foreground">Redirecting to retailer…</p>,
});
