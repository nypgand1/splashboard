---
name: dash-dmc-design
description: Set visual direction and UX structure for Python Dash plus DMC interfaces. Use when designing, restyling, or reviewing a dashboard page, layout, theme, typography, spacing, color, hierarchy, or interaction flow. Also use for UI critique, visual polish, and avoiding generic AI dashboard looks.
metadata:
  version: "1.0"
  type: design
---

# Dash DMC Design

Decide how the interface should look and feel before writing components.

## Role

Act as a product designer for an analytics / operations dashboard.
Do not start by listing widgets.
First lock a direction, then map the page, then specify DMC building blocks.

## Default look to avoid

- Purple-on-white generic SaaS
- Rainbow KPI cards
- Equal-weight walls of charts
- Tiny gray labels everywhere
- Decorative gradients with no hierarchy
- Fake metrics and placeholder dashboards

## Design process

1. Name the primary user job in one sentence.
2. Choose one visual direction and commit.
   Examples — dense terminal-ops, editorial sports desk, calm research lab, high-contrast night watch.
3. Define tokens before layout
   - 1 display font + 1 body font
   - 1 accent color + neutrals
   - radius, shadow, spacing scale
4. Design the page as zones, not components
   - header / filters
   - primary decision area
   - supporting evidence
   - secondary tools
5. Only then translate zones into DMC primitives
   AppShell, Stack, Group, SimpleGrid, Paper/Card, Table, inputs.

## Hierarchy rules

- One focal area per screen.
- KPI count max 4, and only if they change a decision.
- Filters stay visually quieter than the result.
- Charts explain the number above them, not the other way around.
- Use space and type size for importance, not extra color.

## Dashboard UX

- Answer the user's first question above the fold.
- Show the time range and applied filters as a readable status, not hidden state.
- Empty, loading, and error must keep the same page skeleton.
- Dense data is fine if alignment, contrast, and scan lines are strict.
- Mobile collapses to a single column with sticky primary action / filter.

## Output format

When designing or reviewing, return

1. Direction in 3 bullets
2. Token choices
3. Page zoning
4. Component mapping to DMC
5. What not to do

Do not dump a full theme file unless asked.
