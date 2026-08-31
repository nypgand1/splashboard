---
name: dash-dmc-ui
description: Design or refactor Python Dash UIs with dash-mantine-components (DMC). Use when building pages, layouts, themes, forms, tables, charts, dashboards, AppShell, or UX states in a Dash plus DMC project. Also use for dmc, MantineProvider, SimpleGrid, and callback-driven UI work.
metadata:
  version: "1.0"
  stack: dash-dmc
---

# Dash DMC UI

Build and refactor product UI in this repo with Python Dash and DMC only.

## Constraints

- Use `dash` + `dash_mantine_components as dmc`.
- Prefer existing project components, theme, and AppShell over new patterns.
- Do not use React `@mantine/*` APIs (`useForm`, `factory()`, hooks).
- DMC v2 maps to Mantine v8. Do not follow Mantine v9 docs.
- Do not switch to Dash Bootstrap or raw `html.Div` soup unless a DMC component cannot do the job.
- Keep callbacks in Python. Do not invent client-side React state.

## Before editing

1. Find the current shell, theme, and page pattern.
2. Reuse `dmc.MantineProvider`, `dmc.AppShell`, `dmc.Grid` / `dmc.SimpleGrid`, `dmc.Stack`, `dmc.Group`.
3. Match existing spacing, radius, color, and typography tokens.
4. Plan four states for every data view — loading, empty, error, success.

## Layout rules

- Page chrome goes in AppShell (header, navbar, main).
- Vertical rhythm uses `dmc.Stack`.
- Inline actions use `dmc.Group`.
- Responsive cards / KPI / filters use `SimpleGrid` or `Grid`.
- Forms use DMC inputs plus Dash callbacks, not `@mantine/form`.
- Tables use DMC table patterns already in the repo.
- Charts stay in the project's existing chart stack, wrapped by DMC layout.

## UX rules

- One primary action per view.
- Destructive actions need confirmation.
- Filters must be keyboard reachable and show applied state.
- Empty states explain what to do next.
- Errors show a recoverable message, not a raw traceback.
- Loading uses DMC skeletons or loaders, not a blank page.

## Implementation order

1. Agree on the user task and success state.
2. Sketch structure with existing DMC primitives.
3. Implement the happy path first.
4. Add loading / empty / error.
5. Check mobile width and overflow.
6. Run the app and verify callbacks still fire.

## Docs

- DMC LLM docs — https://www.dash-mantine-components.com/assets/llms.txt
- Read `references/conventions.md` if present.
