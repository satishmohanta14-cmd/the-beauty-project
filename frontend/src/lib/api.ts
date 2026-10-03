// Live REST Service connected to FastAPI backend with graceful mock fallback:
//   GET /api/v1/products/:slug · GET /api/v1/dupes/:slug
//   GET /api/v1/ingredients/:slug · GET /go/:offerId
import { PRODUCTS, type Offer, type Product, type Ingredient, type Category, type SkinType, type Retailer } from "./catalog";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const delay = <T,>(v: T, ms = 120) => new Promise<T>((r) => setTimeout(() => r(v), ms));

export const lowestOffer = (p: Product): Offer =>
  [...p.offers].filter((o) => o.inStock).sort((a, b) => a.price - b.price)[0] ?? p.offers[0]!;

export const perMl = (o: Offer) => o.price / (o.ml || 30);
export const inr = (n: number) => "₹" + Math.round(n).toLocaleString("en-IN");
export const inr2 = (n: number) => "₹" + n.toFixed(2);

export function priceHistory(p: Product) {
  let seed = [...p.slug].reduce((a, c) => a + c.charCodeAt(0), 0);
  const rand = () => ((seed = (seed * 9301 + 49297) % 233280) / 233280);
  const base = lowestOffer(p).price;
  const today = new Date();
  return Array.from({ length: 30 }, (_, i) => {
    const d = new Date(today);
    d.setDate(d.getDate() - (29 - i));
    const drift = i === 29 ? 0 : (rand() - 0.45) * 0.12;
    return {
      date: d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" }),
      price: Math.round(base * (1 + drift)),
    };
  });
}

export function similarity(a: Product, b: Product) {
  const A = new Set(a.ingredients.map((i) => i.name));
  const B = new Set(b.ingredients.map((i) => i.name));
  const shared = [...A].filter((x) => B.has(x));
  const union = new Set([...A, ...B]).size;
  const match = Math.round((shared.length / union) * 100);
  const pa = perMl(lowestOffer(a));
  const pb = perMl(lowestOffer(b));
  const savings = Math.round(((pa - pb) / pa) * 100);
  return {
    match,
    savings,
    shared,
    uniqueA: [...A].filter((x) => !B.has(x)),
    uniqueB: [...B].filter((x) => !A.has(x)),
  };
}

// Transform backend product payload into frontend Product contract
function transformBackendProduct(data: any): Product {
  const ingredients: Ingredient[] = (data.ingredients || []).map((i: any) => ({
    name: i.canonical_name || i.inci_name,
    fn: (i.function && i.function[0]) || (i.is_active ? "Active" : "Solvent"),
    comedogenic: i.comedogenic ?? 0,
    safety: (i.comedogenic <= 1 ? "A" : i.comedogenic <= 3 ? "B" : "C") as "A" | "B" | "C",
  }));

  const offers: Offer[] = (data.price_comparison || []).map((o: any, idx: number) => ({
    id: `off-${data.slug}-${idx}`,
    retailer: (o.retailer_name as Retailer) || "Nykaa",
    ml: Number(o.variant_size_ml) || 30,
    price: Number(o.price),
    inStock: o.in_stock ?? true,
    url: o.affiliate_redirect_url ? `${API_BASE}${o.affiliate_redirect_url}` : "#",
  }));

  // Fallback single offer if no retailer comparison row exists
  if (offers.length === 0) {
    offers.push({
      id: `off-${data.slug}-0`,
      retailer: "Nykaa",
      ml: 30,
      price: 599,
      inStock: true,
      url: "#",
    });
  }

  const categoryMap: Record<string, Category> = {
    serum: "Serums",
    serums: "Serums",
    sunscreen: "Sunscreens",
    sunscreens: "Sunscreens",
    moisturizer: "Moisturizers",
    moisturizers: "Moisturizers",
  };
  const category: Category = categoryMap[data.category_id?.toLowerCase()] || "Serums";

  const actives = (data.ingredients || [])
    .filter((i: any) => i.is_active)
    .map((i: any) => i.canonical_name || i.inci_name);

  const sizes = Array.from(new Set(offers.map((o) => o.ml)));

  return {
    slug: data.slug,
    brand: data.brand?.name || "The Beauty Project",
    name: data.name,
    category,
    skinTypes: ["Oily", "Dry", "Sensitive"] as SkinType[],
    actives: actives.length > 0 ? actives : ["Niacinamide"],
    sizes: sizes.length > 0 ? sizes : [30],
    claims: data.claims || ["Fragrance-free", "Cruelty-free"],
    dcs: data.dcs_score || 70,
    hue: 200,
    ingredients,
    offers,
  };
}

export const api = {
  listProducts: async (): Promise<Product[]> => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/products?limit=100`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          const live = data.map(transformBackendProduct);
          // Combine live with any local mocks that aren't duplicated
          const liveSlugs = new Set(live.map((p) => p.slug));
          const remainingMocks = PRODUCTS.filter((p) => !liveSlugs.has(p.slug));
          return [...live, ...remainingMocks];
        }
      }
    } catch (err) {
      console.warn("[TBP Backend API] Falling back to local catalog:", err);
    }
    return delay(PRODUCTS);
  },

  getProduct: async (slug: string): Promise<Product | null> => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/products/${slug}`);
      if (res.ok) {
        const data = await res.json();
        return transformBackendProduct(data);
      }
    } catch (err) {
      console.warn(`[TBP Backend API] Offline or unreachable, falling back to mock catalog for "${slug}":`, err);
    }
    // Graceful fallback to embedded catalog
    return delay(PRODUCTS.find((p) => p.slug === slug) ?? null);
  },

  getIngredients: async (slug: string): Promise<Ingredient[]> => {
    const product = await api.getProduct(slug);
    return product ? product.ingredients : [];
  },

  getDupes: async (slug: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/dupes/${slug}`);
      if (res.ok) {
        const data = await res.json();
        if (data.dupes && data.dupes.length > 0) {
          const currentProd = await api.getProduct(slug);
          return data.dupes.map((d: any) => {
            const transformedDupe = transformBackendProduct({
              slug: d.slug,
              name: d.name,
              brand: { name: d.brand_name, slug: d.brand_name.toLowerCase().replace(/\s+/g, "-") },
              category_id: d.format || "serum",
              price_comparison: d.price ? [{
                retailer_name: "Nykaa",
                variant_size_ml: d.size_ml || 30,
                price: d.price,
                in_stock: true,
                affiliate_redirect_url: d.affiliate_redirect_url,
              }] : [],
            });

            return {
              product: transformedDupe,
              match: Math.round(d.similarity * 100),
              savings: Math.round(-d.price_delta_pct),
              shared: currentProd ? currentProd.actives : [],
              uniqueA: [],
              uniqueB: [],
            };
          });
        }
      }
    } catch (err) {
      console.warn(`[TBP Backend API] Dupes endpoint error for "${slug}", falling back to mock:`, err);
    }

    // Fallback to local mock dupe math
    const p = PRODUCTS.find((x) => x.slug === slug);
    if (!p) return delay([]);
    return delay(
      PRODUCTS.filter((x) => x.slug !== slug && x.category === p.category)
        .map((x) => ({ product: x, ...similarity(p, x) }))
        .sort((a, b) => b.match - a.match),
    );
  },

  resolveOffer: async (offerId: string): Promise<Offer | null> => {
    // Check if offerId is a UUID from backend
    if (offerId.includes("-") && offerId.length >= 32) {
      return {
        id: offerId,
        retailer: "Nykaa",
        ml: 30,
        price: 0,
        inStock: true,
        url: `${API_BASE}/go/${offerId}`,
      };
    }
    return delay(PRODUCTS.flatMap((p) => p.offers).find((o) => o.id === offerId) ?? null);
  },
};
