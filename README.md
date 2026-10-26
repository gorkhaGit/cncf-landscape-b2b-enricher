# CNCF Cloud Native & AI Landscape B2B Lead Enricher

> **High-Speed Async Python B2B Lead & Contact Enricher** extracting 1,500+ Cloud Native, AI/ML, DevOps, Security, and **Kubernetes Certified Service Provider (KCSP)** companies from the official CNCF Landscape, enriched with live website emails, phone numbers, LinkedIn URLs, Crunchbase profiles, and GitHub repositories.

---

## ⚡ Apify Cloud Production Benchmarks

| Metric | Production Benchmark |
| :--- | :--- |
| **Runtime Stack** | Python 3.12 (`httpx` + `BeautifulSoup4` + `PyYAML` + `apify>=4.0.0`) |
| **Headless Browser Overhead** | **None (0 MB)** — 100% Native Async HTTP |
| **Allocated Memory** | **256 MB RAM** (Peak usage: ~95 MB) |
| **Proxy Cost** | **$0.00** (Direct Master YAML + Async Website Crawling) |
| **Cloud Verification Run** | `Succeeded` (`Build 0.1.1` / `Run ID: dbE5CJ050vBRfwe6j`) |

---

## 📊 Scraped Data Evidence (Sample Output)

Full sample files from live runs are included in this repository:
- **JSON Sample:** [`evidence/sample_leads.json`](./evidence/sample_leads.json)
- **CSV Sample:** [`evidence/sample_leads.csv`](./evidence/sample_leads.csv)

### Sample Enriched JSON Record
```json
{
  "vendorName": "Isovalent (Cilium)",
  "category": "Cloud Native Network",
  "subcategory": "Container Network Interface (CNI)",
  "maturityTier": "graduated",
  "website": "[https://isovalent.com](https://isovalent.com)",
  "primaryEmail": "contact@isovalent.com",
  "emails": [
    "contact@isovalent.com",
    "security@isovalent.com"
  ],
  "phones": [],
  "linkedinUrl": "[https://www.linkedin.com/company/isovalent](https://www.linkedin.com/company/isovalent)",
  "twitterUrl": "[https://twitter.com/isovalent](https://twitter.com/isovalent)",
  "githubUrl": "[https://github.com/cilium/cilium](https://github.com/cilium/cilium)",
  "crunchbaseUrl": "[https://www.crunchbase.com/organization/isovalent](https://www.crunchbase.com/organization/isovalent)",
  "contactPageUrl": "[https://isovalent.com/contact/](https://isovalent.com/contact/)",
  "description": "Enterprise eBPF networking, observability, and security powered by Cilium.",
  "scrapedAt": "2026-10-26T05:30:00+00:00"
}
```

---

## 🛠️ Engineering Architecture
1. **Master Ecosystem Ingestion:** Pulls and parses the live CNCF Landscape master YAML specification (`cncf/landscape`), normalizing 1,500+ organizations across `Graduated`, `Incubating`, `Sandbox`, `Member`, and `KCSP` tiers.
2. **Async Contact Enrichment Engine:** Uses an `asyncio.Semaphore(10)` worker pool with `httpx.AsyncClient` to concurrently visit each vendor's homepage and `/contact` page, extracting `mailto:` links, regex-validated business emails, `tel:` numbers, and LinkedIn company URLs.
3. **Strict Schema Sanitization:** Guarantees zero `null` (`None`) type mismatches against `.actor/dataset_schema.json` and `.actor/output_schema.json`.
