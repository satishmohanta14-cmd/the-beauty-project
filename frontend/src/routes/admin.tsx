import { createFileRoute, Link } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import {
  Plus,
  RefreshCw,
  UploadCloud,
  CheckCircle2,
  XCircle,
  ShieldAlert,
  Database,
  BarChart3,
  Layers,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PRODUCTS } from "@/lib/catalog";
import { inr } from "@/lib/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const PRESET_BRANDS = [
  // Indian / Homegrown
  { name: "Minimalist", country: "IN", type: "Indian / Homegrown", parent: "Uprising Science Pvt Ltd" },
  { name: "Dot & Key", country: "IN", type: "Indian / Homegrown", parent: "Dot & Key Wellness (Nykaa)" },
  { name: "The Derma Co", country: "IN", type: "Indian / Homegrown", parent: "Honasa Consumer Ltd" },
  { name: "Aqualogica", country: "IN", type: "Indian / Homegrown", parent: "Honasa Consumer Ltd" },
  { name: "Re'equil", country: "IN", type: "Indian / Homegrown", parent: "Re'equil India Pvt Ltd" },
  { name: "Mamaearth", country: "IN", type: "Indian / Homegrown", parent: "Honasa Consumer Ltd" },
  { name: "Dr. Sheth's", country: "IN", type: "Indian / Homegrown", parent: "Honasa Consumer Ltd" },
  { name: "Lotus Herbals", country: "IN", type: "Indian / Homegrown", parent: "Lotus Herbals Color Cosmetics" },
  { name: "Biotique", country: "IN", type: "Indian / Homegrown", parent: "Bio Veda Action Research Co." },
  { name: "Bombay Shaving Company", country: "IN", type: "Indian / Homegrown", parent: "Visage Lines Personal Care" },
  { name: "Earth Rhythm", country: "IN", type: "Indian / Homegrown", parent: "Earth Rhythm Pvt Ltd" },
  { name: "La Shield", country: "IN", type: "Indian / Pharmacy", parent: "Glenmark Pharmaceuticals" },
  { name: "Suncros", country: "IN", type: "Indian / Pharmacy", parent: "Sun Pharma Laboratories" },
  { name: "Himalaya", country: "IN", type: "Indian / Homegrown", parent: "Himalaya Global Holdings" },
  // International Sold in India
  { name: "Neutrogena", country: "US", type: "International", parent: "Kenvue (Johnson & Johnson)" },
  { name: "La Roche-Posay", country: "FR", type: "International", parent: "L'Oréal" },
  { name: "Cetaphil", country: "CH", type: "International", parent: "Galderma" },
  { name: "Vichy", country: "FR", type: "International", parent: "L'Oréal" },
  { name: "Eucerin", country: "DE", type: "International", parent: "Beiersdorf" },
];

export const Route = createFileRoute("/admin")({
  component: AdminPage,
});

export function AdminPage() {
  const [activeTab, setActiveTab] = useState("products");
  const [products, setProducts] = useState<any[]>([]);
  const [brands, setBrands] = useState<any[]>(PRESET_BRANDS);
  const [queue, setQueue] = useState<any[]>([]);
  const [analytics, setAnalytics] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  // New product form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [newProd, setNewProd] = useState({
    name: "",
    brand_name: "",
    category_id: "serum",
    format: "serum",
    claims: "Fragrance-free, Non-comedogenic",
    raw_ingredients: "",
    size_ml: 30,
    price: 599,
    retailer_name: "Nykaa",
  });

  const fetchAdminData = async () => {
    setLoading(true);
    try {
      // 1. Fetch products
      const pRes = await fetch(`${API_BASE}/api/v1/admin/products`);
      if (pRes.ok) {
        const data = await pRes.json();
        setProducts(data);
      } else {
        // Fallback to local catalog
        setProducts(
          PRODUCTS.map((p) => ({
            id: p.slug,
            name: p.name,
            slug: p.slug,
            brand_name: p.brand,
            category_id: p.category.toLowerCase(),
            dcs_score: p.dcs,
            index_tier: p.dcs >= 70 ? "indexed" : "provisional",
            offer_count: p.offers.length,
            ingredient_count: p.ingredients.length,
          }))
        );
      }

      // 2. Fetch review queue
      const qRes = await fetch(`${API_BASE}/api/v1/admin/queue?status_filter=pending`);
      if (qRes.ok) {
        setQueue(await qRes.json());
      }

      // 3. Fetch analytics
      const aRes = await fetch(`${API_BASE}/api/v1/admin/analytics/archetypes?days=30`);
      if (aRes.ok) {
        const aData = await aRes.json();
        setAnalytics(aData.archetypes || []);
      }
    } catch (err) {
      // Offline fallback
      setProducts(
        PRODUCTS.map((p) => ({
          id: p.slug,
          name: p.name,
          slug: p.slug,
          brand_name: p.brand,
          category_id: p.category.toLowerCase(),
          dcs_score: p.dcs,
          index_tier: p.dcs >= 70 ? "indexed" : "provisional",
          offer_count: p.offers.length,
          ingredient_count: p.ingredients.length,
        }))
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAdminData();
  }, []);

  const handleCreateProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/products`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...newProd,
          claims: newProd.claims.split(",").map((s) => s.trim()),
          size_ml: Number(newProd.size_ml),
          price: Number(newProd.price),
        }),
      });

      if (res.ok) {
        setMsg(`Product "${newProd.name}" successfully added!`);
        setShowAddForm(false);
        setNewProd({
          name: "",
          brand_name: "",
          category_id: "serum",
          format: "serum",
          claims: "Fragrance-free, Non-comedogenic",
          raw_ingredients: "",
          size_ml: 30,
          price: 599,
          retailer_name: "Nykaa",
        });
        fetchAdminData();
      } else {
        const err = await res.json();
        setMsg(`Error: ${err.detail || "Failed to create product"}`);
      }
    } catch {
      setMsg("Backend offline: Added to preview state.");
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerFeed = async (retailer: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/feeds/ingest-sample?retailer=${retailer}`, {
        method: "POST",
      });
      if (res.ok) {
        setMsg(`Triggered automated feed ingestion for ${retailer.toUpperCase()}!`);
      } else {
        setMsg(`Failed to trigger ${retailer} feed.`);
      }
    } catch {
      setMsg("Connection to Celery ingestion queue failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleResolveQueue = async (id: string, action: "approved" | "rejected") => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/queue/${id}/resolve?action=${action}`, {
        method: "POST",
      });
      if (res.ok) {
        setQueue((prev) => prev.filter((item) => item.id !== id));
        setMsg(`Queue candidate ${action}!`);
      }
    } catch {
      setMsg("Failed to update review item.");
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-8">
      {/* Header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b pb-4">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-foreground flex items-center gap-2">
            <Layers className="size-6 text-primary" /> The Beauty Project — Admin Panel
          </h1>
          <p className="text-sm text-muted-foreground">
            Feed Ingestion, Entity Resolution Review, INCI Graph & Programmatic DCS Gating
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchAdminData} disabled={loading}>
            <RefreshCw className={`size-3.5 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button size="sm" onClick={() => setShowAddForm(!showAddForm)}>
            <Plus className="size-3.5 mr-1" /> Add Product
          </Button>
        </div>
      </div>

      {msg && (
        <div className="rounded-md bg-primary/10 border border-primary/20 p-3 text-sm text-foreground flex justify-between items-center">
          <span>{msg}</span>
          <button onClick={() => setMsg(null)} className="text-xs font-bold text-muted-foreground hover:text-foreground">
            ✕
          </button>
        </div>
      )}

      {/* Add Product Modal / Panel */}
      {showAddForm && (
        <Card className="border-primary/40 bg-card shadow-lg">
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Sparkles className="size-4 text-primary" /> New Product Ingestion Form
            </CardTitle>
            <CardDescription>
              Raw INCI text will automatically be normalized and position-encoded into the ingredient graph.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreateProduct} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold uppercase text-muted-foreground">Product Name</label>
                  <input
                    required
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                    placeholder="e.g. 10% Niacinamide Serum"
                    value={newProd.name}
                    onChange={(e) => setNewProd({ ...newProd, name: e.target.value })}
                  />
                </div>
                <div>
                  <label className="text-xs font-bold uppercase text-muted-foreground">Brand Name</label>
                  <input
                    required
                    list="brand-suggestions"
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                    placeholder="e.g. Minimalist, Dot & Key, Cetaphil..."
                    value={newProd.brand_name}
                    onChange={(e) => setNewProd({ ...newProd, brand_name: e.target.value })}
                  />
                  <datalist id="brand-suggestions">
                    {brands.map((b) => (
                      <option key={b.name} value={b.name}>
                        {b.name} ({b.country === "IN" ? "🇮🇳 India" : `🌐 ${b.country}`})
                      </option>
                    ))}
                  </datalist>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="text-xs font-bold uppercase text-muted-foreground">Category</label>
                  <select
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                    value={newProd.category_id}
                    onChange={(e) => setNewProd({ ...newProd, category_id: e.target.value })}
                  >
                    <option value="serum">Serum</option>
                    <option value="sunscreen">Sunscreen</option>
                    <option value="moisturizer">Moisturizer</option>
                    <option value="cleanser">Cleanser</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-bold uppercase text-muted-foreground">Size (ml)</label>
                  <input
                    type="number"
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                    value={newProd.size_ml}
                    onChange={(e) => setNewProd({ ...newProd, size_ml: Number(e.target.value) })}
                  />
                </div>
                <div>
                  <label className="text-xs font-bold uppercase text-muted-foreground">Initial Price (INR)</label>
                  <input
                    type="number"
                    className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                    value={newProd.price}
                    onChange={(e) => setNewProd({ ...newProd, price: Number(e.target.value) })}
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-bold uppercase text-muted-foreground">
                  Raw INCI Ingredients (comma separated)
                </label>
                <textarea
                  required
                  rows={3}
                  className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm"
                  placeholder="Water / Aqua, Niacinamide (Vitamin B3), Glycerin, Zinc PCA, Phenoxyethanol..."
                  value={newProd.raw_ingredients}
                  onChange={(e) => setNewProd({ ...newProd, raw_ingredients: e.target.value })}
                />
              </div>

              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => setShowAddForm(false)}>
                  Cancel
                </Button>
                <Button type="submit" size="sm" disabled={loading}>
                  Save & Ingest to Graph
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="bg-muted p-1">
          <TabsTrigger value="products">Catalog Products ({products.length})</TabsTrigger>
          <TabsTrigger value="brands">Brands Directory ({brands.length})</TabsTrigger>
          <TabsTrigger value="feeds">Automated Feeds (Method 1)</TabsTrigger>
          <TabsTrigger value="queue">
            Review Queue {queue.length > 0 && <Badge variant="destructive" className="ml-2 text-xs">{queue.length}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="analytics">GSC & Search Analytics</TabsTrigger>
        </TabsList>

        {/* Tab 1: Products */}
        <TabsContent value="products">
          <Card>
            <CardHeader>
              <CardTitle>Catalog Products & Completeness</CardTitle>
              <CardDescription>
                Products passing DCS &ge; 70 are tagged indexed; sub-threshold products remain provisional (noindex).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Brand & Name</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>DCS Score</TableHead>
                    <TableHead>Index Tier</TableHead>
                    <TableHead>Live Offers</TableHead>
                    <TableHead>Ingredients</TableHead>
                    <TableHead className="text-right">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {products.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-semibold">
                        <Link to="/p/$slug" params={{ slug: p.slug }} className="hover:underline text-primary">
                          {p.brand_name} {p.name}
                        </Link>
                      </TableCell>
                      <TableCell className="capitalize">{p.category_id}</TableCell>
                      <TableCell>
                        <Badge variant={p.dcs_score >= 70 ? "default" : "secondary"}>
                          {p.dcs_score} / 100
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className={`text-xs font-bold uppercase ${p.index_tier === "indexed" ? "text-green-600" : "text-amber-600"}`}>
                          {p.index_tier}
                        </span>
                      </TableCell>
                      <TableCell>{p.offer_count} offers</TableCell>
                      <TableCell>{p.ingredient_count} INCI</TableCell>
                      <TableCell className="text-right">
                        <Link to="/p/$slug" params={{ slug: p.slug }} className="text-xs text-primary font-bold hover:underline">
                          View &rarr;
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab: Brands Directory */}
        <TabsContent value="brands">
          <Card>
            <CardHeader>
              <CardTitle>Configured Brands Directory ({brands.length})</CardTitle>
              <CardDescription>
                Normalized brand index covering Indian homegrown D2C brands, pharmacy dermat brands, and top international brands in India.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Brand Name</TableHead>
                    <TableHead>Classification</TableHead>
                    <TableHead>Origin</TableHead>
                    <TableHead>Parent Company</TableHead>
                    <TableHead className="text-right">Products</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {brands.map((b) => {
                    const count = products.filter((p) => p.brand_name?.toLowerCase() === b.name?.toLowerCase()).length;
                    return (
                      <TableRow key={b.name}>
                        <TableCell className="font-bold text-foreground flex items-center gap-2">
                          <span>{b.country === "IN" ? "🇮🇳" : "🌐"}</span> {b.name}
                        </TableCell>
                        <TableCell>
                          <Badge variant={b.country === "IN" ? "default" : "outline"}>
                            {b.type || (b.country === "IN" ? "Indian / Homegrown" : "International")}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-semibold text-xs text-muted-foreground uppercase">{b.country}</TableCell>
                        <TableCell className="text-sm text-muted-foreground">{b.parent || b.parent_company || "—"}</TableCell>
                        <TableCell className="text-right font-bold text-sm">
                          {count > 0 ? (
                            <span className="text-primary">{count} in catalog</span>
                          ) : (
                            <span className="text-muted-foreground font-normal">0</span>
                          )}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Method 1 Automated Feeds */}
        <TabsContent value="feeds">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <UploadCloud className="size-5 text-pink-600" /> Nykaa Feed Pipeline
                </CardTitle>
                <CardDescription>Scheduled at 00:00 UTC daily</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  Ingests Indian beauty catalog, standardizes ml volume, matches barcodes/GTINs, and records append-only INR offers.
                </p>
                <Button onClick={() => handleTriggerFeed("nykaa")} disabled={loading} className="w-full" size="sm">
                  Run Nykaa Ingest Task
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <UploadCloud className="size-5 text-amber-600" /> Amazon IN Feed
                </CardTitle>
                <CardDescription>Scheduled at 00:30 UTC daily</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  Processes Amazon PA-API feeds, normalizes affiliate tracking tags, and resolves listings with confidence &ge; 0.85.
                </p>
                <Button onClick={() => handleTriggerFeed("amazon_in")} disabled={loading} className="w-full" size="sm" variant="outline">
                  Run Amazon Ingest Task
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <UploadCloud className="size-5 text-blue-600" /> Sephora Global Feed
                </CardTitle>
                <CardDescription>Scheduled at 01:00 UTC daily</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  Handles multi-currency Tier-1 global catalog (USD/INR), volume conversions (fl oz to ml), and dupe graph edges.
                </p>
                <Button onClick={() => handleTriggerFeed("sephora_us")} disabled={loading} className="w-full" size="sm" variant="outline">
                  Run Sephora Ingest Task
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Tab 3: Review Queue */}
        <TabsContent value="queue">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <ShieldAlert className="size-5 text-amber-500" /> Unresolved Entity Review Queue
              </CardTitle>
              <CardDescription>
                Feed items with confidence score &lt; 0.85 are routed here for human review rather than guessing wrong products.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {queue.length === 0 ? (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  <CheckCircle2 className="size-8 text-green-500 mx-auto mb-2 opacity-60" />
                  Review queue is empty! All recent feed items matched with &ge; 85% confidence.
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Retailer & Listing</TableHead>
                      <TableHead>Candidate Match</TableHead>
                      <TableHead>Confidence</TableHead>
                      <TableHead>Price</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {queue.map((item) => (
                      <TableRow key={item.id}>
                        <TableCell>
                          <div className="font-semibold text-sm">{item.raw_title}</div>
                          <div className="text-xs text-muted-foreground">{item.retailer_name} &bull; {item.raw_size_ml} ml</div>
                        </TableCell>
                        <TableCell className="text-sm font-medium">{item.candidate_product_name || "None"}</TableCell>
                        <TableCell>
                          <Badge variant="secondary">
                            {item.candidate_confidence ? `${Math.round(item.candidate_confidence * 100)}%` : "0%"}
                          </Badge>
                        </TableCell>
                        <TableCell>{item.raw_price ? inr(item.raw_price) : "—"}</TableCell>
                        <TableCell className="text-right space-x-2">
                          <Button size="sm" variant="default" onClick={() => handleResolveQueue(item.id, "approved")}>
                            Approve
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => handleResolveQueue(item.id, "rejected")}>
                            Reject
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 4: Analytics */}
        <TabsContent value="analytics">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BarChart3 className="size-5 text-primary" /> Search Performance by Archetype
              </CardTitle>
              <CardDescription>Live Google Search Console indexability rate, total impressions, and average CTR.</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Archetype</TableHead>
                    <TableHead>Total Pages</TableHead>
                    <TableHead>Indexable Pages</TableHead>
                    <TableHead>Index Rate</TableHead>
                    <TableHead>Impressions</TableHead>
                    <TableHead>Clicks</TableHead>
                    <TableHead>Avg CTR</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {analytics.map((a) => (
                    <TableRow key={a.archetype}>
                      <TableCell className="font-bold capitalize">{a.archetype}</TableCell>
                      <TableCell>{a.total_pages}</TableCell>
                      <TableCell>{a.indexable_pages}</TableCell>
                      <TableCell>
                        <Badge variant={a.index_rate_pct >= 70 ? "default" : "secondary"}>
                          {a.index_rate_pct}%
                        </Badge>
                      </TableCell>
                      <TableCell>{a.total_impressions.toLocaleString()}</TableCell>
                      <TableCell>{a.total_clicks.toLocaleString()}</TableCell>
                      <TableCell>{a.average_ctr_pct}%</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
