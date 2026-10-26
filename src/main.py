from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re
from urllib.parse import urljoin, urlparse, urlunparse

from apify import Actor
from bs4 import BeautifulSoup
import httpx
import yaml

CNCF_YAML_URL = "https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml"

FALLBACK_VENDORS = [
    {
        "name": "Isovalent (Cilium)",
        "category": "Cloud Native Network",
        "subcategory": "Container Network Interface (CNI)",
        "project": "graduated",
        "homepage_url": "https://isovalent.com",
        "repo_url": "https://github.com/cilium/cilium",
        "crunchbase": "https://www.crunchbase.com/organization/isovalent",
        "twitter": "https://twitter.com/isovalent",
        "description": "Enterprise eBPF networking, observability, and security powered by Cilium.",
    },
    {
        "name": "Chainguard",
        "category": "Provisioning",
        "subcategory": "Security & Compliance",
        "project": "member",
        "homepage_url": "https://www.chainguard.dev",
        "repo_url": "https://github.com/chainguard-dev",
        "crunchbase": "https://www.crunchbase.com/organization/chainguard",
        "twitter": "https://twitter.com/chainguard_dev",
        "description": "Zero-CVE container images and software supply chain security.",
    },
    {
        "name": "Teleport",
        "category": "Provisioning",
        "subcategory": "Security & Compliance",
        "project": "commercial",
        "homepage_url": "https://goteleport.com",
        "repo_url": "https://github.com/gravitational/teleport",
        "crunchbase": "https://www.crunchbase.com/organization/gravitational",
        "twitter": "https://twitter.com/goteleport",
        "description": "Identity-native infrastructure access for Kubernetes, SSH, databases, and cloud APIs.",
    },
    {
        "name": "Weaveworks",
        "category": "App Definition and Development",
        "subcategory": "Continuous Integration & Delivery",
        "project": "graduated",
        "homepage_url": "https://www.weave.works",
        "repo_url": "https://github.com/fluxcd/flux2",
        "crunchbase": "https://www.crunchbase.com/organization/weaveworks",
        "twitter": "https://twitter.com/weaveworks",
        "description": "GitOps Kubernetes automation and cloud-native continuous delivery.",
    },
    {
        "name": "tetrate",
        "category": "Orchestration & Management",
        "subcategory": "Service Mesh",
        "project": "member",
        "homepage_url": "https://tetrate.io",
        "repo_url": "https://github.com/tetratelabs",
        "crunchbase": "https://www.crunchbase.com/organization/tetrate",
        "twitter": "https://twitter.com/tetrateio",
        "description": "Enterprise service mesh and application networking built on Istio and Envoy.",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,12}")
BAD_EMAIL_EXT = re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|css|js|woff|ttf|ico|pdf)$", re.I)
BAD_EMAIL_WORDS = re.compile(
    r"(sentry|example|domain|email\.com|yoursite|wixpress|cloudflare|placeholder|u00|cncf\.io|linuxfoundation\.org)",
    re.I,
)


def clean_email(raw: str) -> str:
    e = re.sub(r"^mailto:", "", raw or "", flags=re.I).split("?")[0].strip().lower()
    if not re.match(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,12}$", e):
        return ""
    if BAD_EMAIL_EXT.search(e) or BAD_EMAIL_WORDS.search(e):
        return ""
    return e


def clean_url(raw_url: str) -> str:
    u = str(raw_url or "").strip()
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = f"https://{u}"
    try:
        p = urlparse(u)
        return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
    except Exception:
        return u


async def fetch_text(client: httpx.AsyncClient, url: str, timeout: float = 10.0) -> str:
    try:
        resp = await client.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return ""


def scan_soup_for_contacts(
    soup: BeautifulSoup,
    base_url: str,
    emails: set[str],
    phones: set[str],
    socials: dict[str, str],
) -> None:
    for a in soup.find_all("a", href=True):
        href = (a["href"] or "").strip()
        if not href:
            continue
        low = href.lower()
        if low.startswith("mailto:"):
            ce = clean_email(href)
            if ce:
                emails.add(ce)
        elif low.startswith("tel:"):
            ph = re.sub(r"^tel:", "", href, flags=re.I).strip()
            if 7 <= len(ph) <= 22:
                phones.add(str(ph))
        elif re.search(r"linkedin\.com/(company|in)/", href, re.I) and not socials["linkedinUrl"]:
            socials["linkedinUrl"] = str(href.split("?")[0])
        elif (
            re.search(r"(twitter\.com|x\.com)/[a-z0-9_]+", href, re.I)
            and not re.search(r"intent|share", href, re.I)
            and not socials["twitterUrl"]
        ):
            socials["twitterUrl"] = str(href.split("?")[0])
        elif not socials["contactPageUrl"] and re.search(
            r"/(contact|about|get-in-touch|talk-to-us|company)", href, re.I
        ):
            try:
                 socials["contactPageUrl"] = str(urljoin(base_url, href))
            except Exception:
                pass

    for raw in EMAIL_RE.findall(soup.get_text(" ", strip=True)):
        ce = clean_email(raw)
        if ce:
            emails.add(ce)


async def enrich_vendor_website(
    client: httpx.AsyncClient,
    website_url: str,
    existing_twitter: str = "",
) -> dict:
    emails: set[str] = set()
    phones: set[str] = set()
    socials: dict[str, str] = {
        "linkedinUrl": "",
        "twitterUrl": str(existing_twitter or ""),
        "contactPageUrl": "",
        "metaDescription": "",
    }

    if website_url and not re.search(r"github\.com/", website_url, re.I):
        html = await fetch_text(client, website_url, timeout=8.0)
        if html:
            soup = BeautifulSoup(html, "html.parser")
            meta_tag = soup.find("meta", attrs={"name": "description"}) or soup.find(
                "meta", attrs={"property": "og:description"}
            )
            if meta_tag and meta_tag.get("content"):
                socials["metaDescription"] = str(meta_tag["content"]).strip()

            scan_soup_for_contacts(soup, website_url, emails, phones, socials)

            if not emails and socials["contactPageUrl"]:
                contact_html = await fetch_text(client, socials["contactPageUrl"], timeout=6.0)
                if contact_html:
                    scan_soup_for_contacts(
                        BeautifulSoup(contact_html, "html.parser"),
                        socials["contactPageUrl"],
                        emails,
                        phones,
                        socials,
                    )

    sorted_emails = sorted(emails)[:10]
    return {
        "primaryEmail": sorted_emails[0] if sorted_emails else "",
        "emails": sorted_emails,
        "phones": sorted(phones)[:5],
        "linkedinUrl": str(socials["linkedinUrl"] or ""),
        "twitterUrl": str(socials["twitterUrl"] or ""),
        "contactPageUrl": str(socials["contactPageUrl"] or ""),
        "metaDescription": str(socials["metaDescription"] or ""),
    }


def sanitize_record(record: dict) -> dict:
    clean: dict = {}
    for k, v in record.items():
        if v is None:
            clean[k] = ""
        elif isinstance(v, list):
            clean[k] = [str(x) for x in v if x is not None and str(x).strip() != ""]
        elif isinstance(v, int):
            clean[k] = int(v)
        else:
            clean[k] = str(v)
    return clean


def parse_cncf_landscape_yaml(raw_yaml: str) -> list[dict]:
    vendors: list[dict] = []
    seen_names: set[str] = set()
    try:
        data = yaml.safe_load(raw_yaml)
        landscape_list = data.get("landscape", []) if isinstance(data, dict) else []
        for cat in landscape_list:
            if not isinstance(cat, dict):
                continue
            cat_name = str(cat.get("name") or "Cloud Native")
            subcats = cat.get("subcategories", []) or []
            for sub in subcats:
                if not isinstance(sub, dict):
                    continue
                sub_name = str(sub.get("name") or "General")
                items = sub.get("items", []) or []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    v_name = str(item.get("name") or "").strip()
                    homepage = clean_url(str(item.get("homepage_url") or ""))
                    if not v_name or not homepage:
                        continue
                    dedupe_key = f"{v_name.lower()}::{homepage.lower()}"
                    if dedupe_key in seen_names:
                        continue
                    seen_names.add(dedupe_key)

                    extra = item.get("extra", {}) if isinstance(item.get("extra"), dict) else {}
                    raw_tags = extra.get("summary_tags") or ""
                    if isinstance(raw_tags, str):
                        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
                    elif isinstance(raw_tags, list):
                        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
                    else:
                        tags = []

                    project_tier = str(item.get("project") or "commercial").strip()
                    vendors.append(
                        {
                            "name": v_name,
                            "category": cat_name,
                            "subcategory": sub_name,
                            "project": project_tier,
                            "homepage_url": homepage,
                            "repo_url": clean_url(str(item.get("repo_url") or "")),
                            "crunchbase": clean_url(str(item.get("crunchbase") or "")),
                            "twitter": clean_url(str(item.get("twitter") or "")),
                            "description": str(
                                item.get("description") or extra.get("summary_use_case") or ""
                            ).strip(),
                            "business_use_case": str(extra.get("summary_business_use_case") or "").strip(),
                            "personas": str(extra.get("summary_personas") or "").strip(),
                            "tags": tags[:15],
                        }
                    )
    except Exception as exc:
        Actor.log.warning(f"YAML parse warning: {exc}")
    return vendors


async def process_vendor(
    item: dict,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    enrich_contacts: bool,
) -> dict:
    website = str(item.get("homepage_url") or "")
    existing_twitter = str(item.get("twitter") or "")

    if enrich_contacts and website:
        async with semaphore:
            contacts = await enrich_vendor_website(client, website, existing_twitter)
    else:
        contacts = {
            "primaryEmail": "",
            "emails": [],
            "phones": [],
            "linkedinUrl": "",
            "twitterUrl": existing_twitter,
            "contactPageUrl": "",
            "metaDescription": "",
        }

    desc = str(item.get("description") or contacts.get("metaDescription") or "").strip()
    record = {
        "vendorName": str(item.get("name") or ""),
        "category": str(item.get("category") or ""),
        "subcategory": str(item.get("subcategory") or ""),
        "maturityTier": str(item.get("project") or "commercial"),
        "website": website,
        "primaryEmail": str(contacts.get("primaryEmail") or ""),
        "emails": list(contacts.get("emails") or []),
        "phones": list(contacts.get("phones") or []),
        "linkedinUrl": str(contacts.get("linkedinUrl") or ""),
        "twitterUrl": str(contacts.get("twitterUrl") or ""),
        "githubUrl": str(item.get("repo_url") or ""),
        "crunchbaseUrl": str(item.get("crunchbase") or ""),
        "contactPageUrl": str(contacts.get("contactPageUrl") or ""),
        "description": desc[:500],
        "businessUseCase": str(item.get("business_use_case") or "")[:500],
        "targetPersonas": str(item.get("personas") or ""),
        "tags": list(item.get("tags") or []),
        "scrapedAt": datetime.now(timezone.utc).isoformat(),
    }
    return sanitize_record(record)


async def main() -> None:
    async with Actor:
        actor_input = await Actor.get_input() or {}
        category_filter = str(actor_input.get("categoryFilter") or "").strip().lower()
        maturity_filter = str(actor_input.get("maturityFilter") or "all").strip().lower()
        search_query = str(actor_input.get("searchQuery") or "").strip().lower()
        max_items = int(actor_input.get("maxItems") or 25)
        enrich_contacts = bool(actor_input.get("enrichWebsiteContacts", True))

        Actor.log.info(
            f"Starting CNCF Cloud Native & AI Landscape Enricher "
            f"(maxItems={max_items}, category='{category_filter}', maturity='{maturity_filter}', enrich={enrich_contacts})"
        )

        async with httpx.AsyncClient() as client:
            Actor.log.info("Fetching official CNCF Landscape master YAML dataset...")
            raw_yaml = await fetch_text(client, CNCF_YAML_URL, timeout=20.0)
            vendors = parse_cncf_landscape_yaml(raw_yaml) if raw_yaml else []
            if not vendors:
                Actor.log.warning("Using curated fallback CNCF vendors list.")
                vendors = list(FALLBACK_VENDORS)

            Actor.log.info(f"Loaded {len(vendors)} total unique Cloud Native & AI vendors from CNCF Landscape.")

            filtered: list[dict] = []
            for v in vendors:
                if category_filter:
                    cat_hay = f"{v.get('category', '')} {v.get('subcategory', '')}".lower()
                    if category_filter not in cat_hay:
                        continue
                if maturity_filter != "all":
                    if maturity_filter != str(v.get("project") or "commercial").lower():
                        continue
                if search_query:
                    hay = (
                        f"{v.get('name', '')} {v.get('category', '')} {v.get('subcategory', '')} "
                        f"{v.get('description', '')} {' '.join(v.get('tags', []))} {v.get('homepage_url', '')}"
                    ).lower()
                    if search_query not in hay:
                        continue
                filtered.append(v)
                if len(filtered) >= max_items:
                    break

            Actor.log.info(f"Queued {len(filtered)} matching CNCF vendors for live B2B website contact enrichment.")

            semaphore = asyncio.Semaphore(10)
            saved_count = 0
            batch_size = 10

            for i in range(0, len(filtered), batch_size):
                chunk = filtered[i : i + batch_size]
                tasks = [
                    process_vendor(item, client, semaphore, enrich_contacts)
                    for item in chunk
                ]
                results = await asyncio.gather(*tasks)
                for record in results:
                    if saved_count >= max_items:
                        break
                    try:
                        await Actor.push_data(record)
                        saved_count += 1
                        try:
                            await Actor.charge(event_name="vendor-enriched", count=1)
                        except Exception:
                            pass
                        Actor.log.info(
                            f"[{saved_count}/{max_items}] Enriched CNCF Vendor: "
                            f"{record['vendorName']} ({record['website']}) | "
                            f"Emails: {len(record['emails'])} | LinkedIn: {'Yes' if record['linkedinUrl'] else 'No'}"
                        )
                    except Exception as exc:
                        Actor.log.warning(f"Skipped invalid record: {exc}")

        Actor.log.info(f"Finished run! Total CNCF Cloud Native & AI B2B leads pushed: {saved_count}")
