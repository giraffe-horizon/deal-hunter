# Phase 5: Template DRY & Frontend Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate template duplication, extract inline JavaScript, delete dead templates. Target: ~3,278 → ~2,400 lines.

**Architecture:** New macros in `macros.html`, dead template deletion, inline JS extracted to static files.

**Tech Stack:** Jinja2, JavaScript, HTMX, Chart.js, Tailwind CSS (all CDN, no build step).

---

### Task 1: Delete Dead Templates

**Files:**
- Delete: `dashboard/templates/profile_detail.html`
- Delete: `dashboard/templates/profile_edit.html`
- Delete: `dashboard/templates/profile_yaml.html`

These are unused — the unified profile page (`profile_unified.html` + tab partials) replaced them.

- [ ] **Step 1: Verify no references**
- [ ] **Step 2: Delete the 3 files**
- [ ] **Step 3: Run tests, commit**

```bash
git rm dashboard/templates/profile_detail.html dashboard/templates/profile_edit.html dashboard/templates/profile_yaml.html
git commit -m "chore: delete dead profile templates replaced by unified page"
```

---

### Task 2: Extract Inline JS — Price Chart

**Files:**
- Create: `dashboard/static/js/price-chart.js`
- Modify: `dashboard/templates/deal_detail.html`

Extract the inline `<script>` block from `deal_detail.html` that initializes Chart.js price history chart into `dashboard/static/js/price-chart.js`. Use `data-*` attributes to pass deal data.

- [ ] **Step 1: Read deal_detail.html, identify inline chart JS**
- [ ] **Step 2: Create price-chart.js with extracted code**
- [ ] **Step 3: Update template to use external script + data attributes**
- [ ] **Step 4: Run tests, commit**

```bash
git commit -m "refactor(frontend): extract price chart JS to static file"
```

---

### Task 3: Extract Inline JS — Sparklines

**Files:**
- Create: `dashboard/static/js/sparklines.js`
- Modify: templates that have inline sparkline init code

Extract the `createSparkline()` initialization loop from templates into a shared static JS file.

- [ ] **Step 1: Find all templates with sparkline init code**
- [ ] **Step 2: Create sparklines.js**
- [ ] **Step 3: Update templates**
- [ ] **Step 4: Run tests, commit**

```bash
git commit -m "refactor(frontend): extract sparkline init to static JS file"
```

---

### Task 4: Add Macros — Score Rules & Budget

**Files:**
- Modify: `dashboard/templates/macros.html`
- Modify: templates that duplicate score_rules and budget display

Add macros for commonly repeated template patterns:
- `score_rules_table(rules, penalties, editable)` — duplicated across profile views
- `budget_display(min_val, max_val, currency)` — duplicated in profile views

- [ ] **Step 1: Identify duplication across templates**
- [ ] **Step 2: Create macros**
- [ ] **Step 3: Update templates to use macros**
- [ ] **Step 4: Run tests, commit**

```bash
git commit -m "refactor(templates): add score_rules_table and budget macros"
```

---

### Task 5: Final Verification + CLAUDE.md

- [ ] **Step 1: Count template lines (target: <2,800)**
- [ ] **Step 2: Run full test suite**
- [ ] **Step 3: Update CLAUDE.md**
- [ ] **Step 4: Commit**

```bash
git commit -m "docs: update CLAUDE.md for Phase 5 template cleanup"
```
