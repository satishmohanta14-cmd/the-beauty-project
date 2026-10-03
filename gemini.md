# Gemini Context & Project Architecture: The Beauty Project Backend

## Project Vision & Context
This project is a high-performance programmatic beauty and skincare publisher platform designed around a hybrid SEO and monetization play (Tier-1 global queries + India commercial intent).
The backend serves as the single source of truth for:
- A normalized ingredient graph (~3,000 canonical INCI names).
- A 25,000+ SKU multi-retailer product and offer index.
- An automated vector similarity dupe engine.
- An programmatic page indexability gate (Data Completeness Score).
- Hybrid market and locale routing (India / Tier-1 Global).

---

## Technical Stack Guidelines

- **Primary Database**: PostgreSQL with `pgvector` extension.
- **Backend / Workers**: Python 3.11+ using FastAPI (API layer) and Celery + Redis (asynchronous processing and ingestion).
- **Search & Filtering**: Typesense or Meilisearch for ultra-low latency faceted lookups.
- **Edge & Frontend Interface**: Next.js (SSR / ISR) via Cloudflare edge cache.
- **External Integrations**: Google Search Console (GSC) API, Affiliate Feeds (Cuelinks, Admitad, Impact, Rakuten, Amazon PA-API).

---

## Critical Architecture Principles

### 1. The Append-Only Price Invariant
- **Rule**: Never update or overwrite rows in the `offer` table.
- **Implementation**: Every retailer scrape or feed import creates a new timestamped observation record. Price history is a first-class feature required for schema and analytics.

### 2. Ingredient Position Encoding
- **Rule**: `product_ingredient.position` is mandatory.
- **Implementation**: Position strictly represents the descending concentration order from the INCI label. It directly weights the dupe vector calculation and skin fit scoring algorithms.

### 3. Automated Indexability Gate (DCS)
- **Rule**: Every programmatic page has a calculated Data Completeness Score (DCS).
- **Threshold**: Pages with DCS < 70 must be tagged `noindex, follow` in sitemaps and API metadata responses.
- **Scoring Rubric**:
  - Full parsed ingredient list: **+30 points** (Mandatory).
  - >= 2 live retailer offers: **+20 points** (Mandatory for `/p/` archetype).
  - >= 15 structured skin-profile reviews: **+20 points**.
  - >= 30 days of recorded price history: **+10 points**.
  - Media & variant coverage: **+10 points**.
  - Expert / Chemist review annotation: **+10 points** (Mandatory for `/ingredient/` and `/best/` archetypes).

### 4. Hybrid Routing Invariant
- **Rule**: Support global and regional pages from a unified SKU database.
- **Fields**: Entities must maintain `markets[]` (e.g., `["IN", "US"]`) and pages must carry `locale` attributes to output correct currency, offer ranking, and `hreflang` structures.

---

## Core Database Schema Reference

```sql
-- Brands
CREATE TABLE brand (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    country VARCHAR(100),
    parent_company VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Products
CREATE TABLE product (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID REFERENCES brand(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    category_id VARCHAR(100) NOT NULL,
    format VARCHAR(100), -- serum, cream, gel, etc.
    claims TEXT[],
    markets VARCHAR(10)[] DEFAULT ARRAY['IN'],
    dcs_score INT DEFAULT 0,
    index_tier VARCHAR(50) DEFAULT 'provisional',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Variants (SKU level)
CREATE TABLE variant (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES product(id) ON DELETE CASCADE,
    size_ml NUMERIC(8,2) NOT NULL,
    shade_name VARCHAR(100),
    gtin VARCHAR(50), -- barcode/EAN/UPC for deterministic matching
    mrp NUMERIC(10,2),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Normalized Ingredient Graph
CREATE TABLE ingredient (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inci_name VARCHAR(255) UNIQUE NOT NULL,
    canonical_name VARCHAR(255) NOT NULL,
    synonyms TEXT[],
    cas_no VARCHAR(100),
    function TEXT[],
    evidence_grade VARCHAR(10), -- A, B, C, D
    comedogenic INT CHECK (comedogenic BETWEEN 0 AND 5),
    irritancy INT CHECK (irritancy BETWEEN 0 AND 5),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Product Ingredients (Order denotes concentration)
CREATE TABLE product_ingredient (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID REFERENCES product(id) ON DELETE CASCADE,
    ingredient_id UUID REFERENCES ingredient(id) ON DELETE RESTRICT,
    position INT NOT NULL,
    is_active BOOLEAN DEFAULT false,
    UNIQUE (product_id, position)
);

-- Retailers & Feeds
CREATE TABLE retailer (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    market VARCHAR(10) NOT NULL, -- IN, US, UK, etc.
    affiliate_network VARCHAR(100),
    commission_rate NUMERIC(5,2),
    feed_url TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Append-Only Offers (Never update existing records)
CREATE TABLE offer (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant_id UUID REFERENCES variant(id) ON DELETE CASCADE,
    retailer_id UUID REFERENCES retailer(id) ON DELETE CASCADE,
    price NUMERIC(10,2) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    in_stock BOOLEAN DEFAULT true,
    affiliate_url TEXT NOT NULL,
    seen_at TIMESTAMPTZ DEFAULT now()
);

-- Vector Similarity Dupe Edges
CREATE TABLE dupe_edge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_a UUID REFERENCES product(id) ON DELETE CASCADE,
    product_b UUID REFERENCES product(id) ON DELETE CASCADE,
    similarity NUMERIC(5,4) NOT NULL,
    price_delta_pct NUMERIC(6,2) NOT NULL,
    method_version VARCHAR(50) NOT NULL,
    computed_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (product_a, product_b, method_version)
);

-- Programmatic Page State
CREATE TABLE page (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    archetype VARCHAR(50) NOT NULL, -- product, ingredient, dupe, conflict, vs, under
    url VARCHAR(500) UNIQUE NOT NULL,
    locale VARCHAR(10) NOT NULL,
    entity_refs UUID[],
    dcs_score INT DEFAULT 0,
    indexable BOOLEAN DEFAULT false,
    first_indexed_at TIMESTAMPTZ
);
```
