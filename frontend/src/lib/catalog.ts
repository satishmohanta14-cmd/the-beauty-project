export type Category = "Serums" | "Sunscreens" | "Moisturizers" | "Cleansers";
export type SkinType = "Oily" | "Dry" | "Sensitive";
export type Retailer = "Nykaa" | "Amazon" | "Tira" | "Sephora";

export interface Ingredient {
  name: string;
  fn: string;
  comedogenic: number;
  safety: "A" | "B" | "C";
}

export interface Offer {
  id: string;
  retailer: Retailer;
  ml: number;
  price: number;
  inStock: boolean;
  url: string;
}

export interface Product {
  slug: string;
  brand: string;
  name: string;
  category: Category;
  skinTypes: SkinType[];
  actives: string[];
  sizes: number[];
  claims: string[];
  dcs: number;
  hue: number;
  ingredients: Ingredient[];
  offers: Offer[];
}

const I = (name: string, fn: string, comedogenic = 0, safety: Ingredient["safety"] = "A"): Ingredient => ({ name, fn, comedogenic, safety });

const base = {
  water: I("Aqua", "Solvent"),
  glycerin: I("Glycerin", "Humectant"),
  niac: I("Niacinamide", "Barrier / Brightening"),
  zinc: I("Zinc PCA", "Sebum control"),
  ha: I("Sodium Hyaluronate", "Humectant"),
  pg: I("Propanediol", "Solvent / Humectant"),
  vitc: I("Ethyl Ascorbic Acid", "Antioxidant", 0, "A"),
  vite: I("Tocopherol", "Antioxidant", 2),
  ferulic: I("Ferulic Acid", "Antioxidant"),
  cer: I("Ceramide NP", "Barrier repair"),
  chol: I("Cholesterol", "Emollient", 0),
  squa: I("Squalane", "Emollient", 1),
  shea: I("Butyrospermum Parkii Butter", "Occlusive", 2),
  pheno: I("Phenoxyethanol", "Preservative", 0, "B"),
  frag: I("Parfum", "Fragrance", 0, "C"),
  zno: I("Zinc Oxide", "UV filter", 1),
  avo: I("Avobenzone", "UV filter", 0, "B"),
  tino: I("Bis-Ethylhexyloxyphenol Methoxyphenyl Triazine", "UV filter"),
  uvinul: I("Diethylamino Hydroxybenzoyl Hexyl Benzoate", "UV filter"),
  octo: I("Octocrylene", "UV filter", 0, "B"),
  cica: I("Centella Asiatica Extract", "Soothing"),
  panth: I("Panthenol", "Soothing"),
  sal: I("Salicylic Acid", "Exfoliant (BHA)"),
  aha: I("Glycolic Acid", "Exfoliant (AHA)", 0, "B"),
  ret: I("Retinol", "Cell turnover", 0, "B"),
  bak: I("Bakuchiol", "Retinol alternative"),
  pept: I("Palmitoyl Tripeptide-1", "Peptide"),
  xanthan: I("Xanthan Gum", "Thickener"),
  cetearyl: I("Cetearyl Alcohol", "Emulsifier", 2),
  dime: I("Dimethicone", "Slip agent", 1),
};

const offers = (slug: string, ml: number, prices: [Retailer, number, boolean?][]): Offer[] =>
  prices.map(([retailer, price, stock = true], i) => ({
    id: `${slug}-${retailer.toLowerCase()}-${i}`,
    retailer,
    ml,
    price,
    inStock: stock,
    url: `https://www.${retailer.toLowerCase()}.com/search?q=${encodeURIComponent(slug)}`,
  }));

export const PRODUCTS: Product[] = [
  {
    slug: "minimalist-niacinamide-10",
    brand: "Minimalist",
    name: "Niacinamide 10% + Zinc 1% Serum",
    category: "Serums",
    skinTypes: ["Oily", "Sensitive"],
    actives: ["Niacinamide 10%", "Zinc PCA 1%"],
    sizes: [30],
    claims: ["Fragrance-free", "Non-comedogenic", "Dermat tested"],
    dcs: 92,
    hue: 210,
    ingredients: [base.water, base.niac, base.pg, base.zinc, base.glycerin, base.xanthan, base.pheno],
    offers: offers("minimalist-niacinamide-10", 30, [["Nykaa", 599], ["Amazon", 549], ["Tira", 579], ["Sephora", 599, false]]),
  },
  {
    slug: "the-ordinary-niacinamide-10",
    brand: "The Ordinary",
    name: "Niacinamide 10% + Zinc 1%",
    category: "Serums",
    skinTypes: ["Oily"],
    actives: ["Niacinamide 10%", "Zinc PCA 1%"],
    sizes: [30, 60],
    claims: ["Vegan", "Cruelty-free"],
    dcs: 88,
    hue: 30,
    ingredients: [base.water, base.niac, base.pg, base.zinc, base.xanthan, I("Tamarindus Indica Seed Gum", "Film former"), base.pheno],
    offers: offers("the-ordinary-niacinamide-10", 30, [["Nykaa", 1150], ["Amazon", 1090], ["Sephora", 1200], ["Tira", 1125]]),
  },
  {
    slug: "dot-key-vitamin-c-e",
    brand: "Dot & Key",
    name: "Vitamin C + E Super Bright Serum",
    category: "Serums",
    skinTypes: ["Dry", "Oily"],
    actives: ["Vitamin C 10%", "Vitamin E", "Ferulic Acid"],
    sizes: [20, 30],
    claims: ["Brightening", "Paraben-free"],
    dcs: 79,
    hue: 40,
    ingredients: [base.water, base.vitc, base.pg, base.glycerin, base.vite, base.ferulic, base.ha, base.frag, base.pheno],
    offers: offers("dot-key-vitamin-c-e", 20, [["Nykaa", 645], ["Amazon", 599], ["Tira", 629]]),
  },
  {
    slug: "skinceuticals-ce-ferulic",
    brand: "SkinCeuticals",
    name: "C E Ferulic",
    category: "Serums",
    skinTypes: ["Dry"],
    actives: ["L-Ascorbic Acid 15%", "Vitamin E 1%", "Ferulic Acid 0.5%"],
    sizes: [30],
    claims: ["Patented antioxidant", "Clinically tested"],
    dcs: 95,
    hue: 25,
    ingredients: [base.water, I("Ascorbic Acid", "Antioxidant"), base.glycerin, base.vite, base.ferulic, base.ha, base.pheno],
    offers: offers("skinceuticals-ce-ferulic", 30, [["Sephora", 13900], ["Nykaa", 13500], ["Amazon", 12990]]),
  },
  {
    slug: "re-equil-oxybenzone-free-spf50",
    brand: "Re'equil",
    name: "Oxybenzone & OMC Free Sunscreen SPF 50",
    category: "Sunscreens",
    skinTypes: ["Oily", "Sensitive"],
    actives: ["Tinosorb S", "Uvinul A Plus", "Zinc Oxide"],
    sizes: [50],
    claims: ["PA+++", "No white cast", "Reef safe"],
    dcs: 86,
    hue: 50,
    ingredients: [base.water, base.tino, base.uvinul, base.zno, base.glycerin, base.dime, base.niac, base.pheno],
    offers: offers("re-equil-oxybenzone-free-spf50", 50, [["Nykaa", 795], ["Amazon", 745], ["Tira", 780]]),
  },
  {
    slug: "la-roche-posay-anthelios-uvmune",
    brand: "La Roche-Posay",
    name: "Anthelios UVMune 400 Fluid SPF 50+",
    category: "Sunscreens",
    skinTypes: ["Sensitive", "Dry", "Oily"],
    actives: ["Mexoryl 400", "Tinosorb S", "Uvinul A Plus"],
    sizes: [50],
    claims: ["PA++++", "Water resistant", "Fragrance-free"],
    dcs: 91,
    hue: 200,
    ingredients: [base.water, base.tino, base.uvinul, base.octo, base.glycerin, base.dime, I("Methoxypropylamino Cyclohexenylidene Ethoxyethylcyanoacetate", "UV filter"), base.pheno],
    offers: offers("la-roche-posay-anthelios-uvmune", 50, [["Nykaa", 1950], ["Sephora", 2100], ["Amazon", 1879], ["Tira", 1990]]),
  },
  {
    slug: "cerave-moisturising-cream",
    brand: "CeraVe",
    name: "Moisturising Cream",
    category: "Moisturizers",
    skinTypes: ["Dry", "Sensitive"],
    actives: ["Ceramides 1, 3, 6-II", "Hyaluronic Acid"],
    sizes: [50, 177, 340],
    claims: ["MVE technology", "Accepted by NEA"],
    dcs: 90,
    hue: 215,
    ingredients: [base.water, base.glycerin, base.cetearyl, base.cer, base.chol, base.ha, base.dime, base.pheno],
    offers: offers("cerave-moisturising-cream", 50, [["Nykaa", 425], ["Amazon", 399], ["Tira", 415], ["Sephora", 450]]),
  },
  {
    slug: "minimalist-ceramides-moisturizer",
    brand: "Minimalist",
    name: "Sepicalm 3% + Oats Moisturizer",
    category: "Moisturizers",
    skinTypes: ["Sensitive", "Dry"],
    actives: ["Ceramides", "Oat Extract", "Panthenol"],
    sizes: [50],
    claims: ["Fragrance-free", "Barrier repair"],
    dcs: 84,
    hue: 160,
    ingredients: [base.water, base.glycerin, base.cetearyl, base.cer, base.squa, base.panth, base.ha, base.pheno],
    offers: offers("minimalist-ceramides-moisturizer", 50, [["Nykaa", 349], ["Amazon", 329], ["Tira", 345]]),
  },
  {
    slug: "drunk-elephant-protini",
    brand: "Drunk Elephant",
    name: "Protini Polypeptide Cream",
    category: "Moisturizers",
    skinTypes: ["Dry"],
    actives: ["Signal Peptides", "Amino Acids"],
    sizes: [50],
    claims: ["Clean-compatible", "Fragrance-free"],
    dcs: 82,
    hue: 330,
    ingredients: [base.water, base.glycerin, base.cetearyl, base.pept, base.squa, base.panth, base.dime, base.pheno],
    offers: offers("drunk-elephant-protini", 50, [["Sephora", 6100], ["Nykaa", 5950], ["Tira", 5990]]),
  },
  {
    slug: "deconstruct-bakuchiol-serum",
    brand: "Deconstruct",
    name: "Bakuchiol + Peptide Night Serum",
    category: "Serums",
    skinTypes: ["Sensitive", "Dry"],
    actives: ["Bakuchiol 1%", "Peptides"],
    sizes: [30],
    claims: ["Pregnancy safe", "Non-irritating"],
    dcs: 74,
    hue: 280,
    ingredients: [base.water, base.squa, base.bak, base.pept, base.glycerin, base.vite, base.pheno],
    offers: offers("deconstruct-bakuchiol-serum", 30, [["Nykaa", 599], ["Amazon", 569, false]]),
  },
];

export const CATEGORIES: Category[] = ["Serums", "Sunscreens", "Moisturizers", "Cleansers"];
export const SKIN_TYPES: SkinType[] = ["Oily", "Dry", "Sensitive"];
export const BUDGETS = [
  { label: "Under ₹500", max: 500 },
  { label: "Under ₹1,000", max: 1000 },
];
