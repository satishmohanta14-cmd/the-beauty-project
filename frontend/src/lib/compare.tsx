import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

interface Ctx {
  items: string[];
  toggle: (slug: string) => void;
  remove: (slug: string) => void;
  clear: () => void;
  has: (slug: string) => boolean;
}
const CompareCtx = createContext<Ctx | null>(null);
const KEY = "cosmo-compare";
const MAX = 4;

export function CompareProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<string[]>([]);
  useEffect(() => {
    try {
      setItems(JSON.parse(localStorage.getItem(KEY) || "[]"));
    } catch {}
  }, []);
  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(items));
  }, [items]);
  const toggle = (s: string) =>
    setItems((c) => (c.includes(s) ? c.filter((x) => x !== s) : c.length >= MAX ? c : [...c, s]));
  return (
    <CompareCtx.Provider
      value={{
        items,
        toggle,
        remove: (s) => setItems((c) => c.filter((x) => x !== s)),
        clear: () => setItems([]),
        has: (s) => items.includes(s),
      }}
    >
      {children}
    </CompareCtx.Provider>
  );
}

export const useCompare = () => {
  const c = useContext(CompareCtx);
  if (!c) throw new Error("CompareProvider missing");
  return c;
};
