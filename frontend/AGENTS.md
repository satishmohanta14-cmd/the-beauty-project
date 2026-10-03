<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

- All product data flows through the mock service in src/lib/api.ts (mirrors /api/v1 endpoints) so it can be swapped for a real backend without touching pages.
- Compare selection lives in a client context (src/lib/compare.tsx) persisted to localStorage; the drawer is mounted once in __root.
