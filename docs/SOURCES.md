# Spindeln — Data Sources & Legal Basis

## Legal Framework

Sweden's **offentlighetsprincipen** (principle of public access) makes nearly all personal data publicly accessible through government agencies. Commercial services like Ratsit.se and Hitta.se aggregate this public data and expose it via their websites.

Key legal principles:
- Swedish public records are accessible to everyone under **Tryckfrihetsförordningen** (Freedom of the Press Act)
- Income, tax, address, property, and company data are public information
- Services like Ratsit.se register as news outlets (utgivningsbevis) to bypass GDPR Article 85
- Scraping publicly accessible data for personal use is permitted under Swedish law

---

## Data Sources

### Public Records (Swedish Government / Commercial Aggregators)

| Source | URL | Method | Data | Auth Required |
|--------|-----|--------|------|---------------|
| Ratsit | ratsit.se | Crawl4AI scrape | Income, tax, family, address history, company roles, payment remarks | No |
| Hitta | hitta.se | Crawl4AI scrape | Phone, address, neighbors, map coordinates | No |
| Eniro | eniro.se | Crawl4AI scrape | Phone, address, business listings | No |
| Merinfo | merinfo.se | Crawl4AI scrape | Age, property estimate, nearby residents | No |
| Bolagsverket | data.bolagsverket.se | Free API | Company registrations, board positions, annual reports | No |
| Riksdagen | data.riksdagen.se | Free API | Political activity, votes, motions | No |
| Polisen | polisen.se/api | Free API | Local police events | No |
| SCB | api.scb.se | Free API | Area demographics, income statistics | No |

### Social Media Discovery

All discovered via SearXNG metasearch + Crawl4AI scraping:

| Platform | Search Pattern | Data |
|----------|---------------|------|
| Facebook | `"name" site:facebook.com city` | Public profile, posts |
| Instagram | `"name" site:instagram.com` | Public profile, bio |
| LinkedIn | `"name" site:linkedin.com Sweden` | Professional profile |
| Twitter/X | `"name" site:twitter.com OR site:x.com` | Public tweets, bio |
| YouTube | SearXNG search | Channel, videos |
| TikTok | `"name" site:tiktok.com` | Public profile |
| GitHub | SearXNG + API | Repositories, contributions |
| Reddit | SearXNG search | Posts, comments |
| Flashback | `"name" site:flashback.org` | Swedish forum posts |

### Breach / Exposure Databases

| Source | URL | Method | Data | Auth Required |
|--------|-----|--------|------|---------------|
| Have I Been Pwned | haveibeenpwned.com/api/v3 | Free API | Email breach history | API key (free) |
| Intelligence X | intelx.io | Free tier API | Dark web, paste sites, leaks | API key (free tier) |
| Hudson Rock | cavalier.hudsonrock.com | Free API | Infostealer malware exposure | No |
| Ahmia | ahmia.fi | Clearnet scrape | Tor .onion site search results | No |
| Pastebin | pastebin.com | SearXNG search | Paste site content | No |

### News & Web

| Source | Method | Data |
|--------|--------|------|
| Swedish news (SVT, SR, DN, etc.) | SearXNG news search | Person mentions in media |
| Brottsplatskartan | Crawl4AI scrape | Crime events near address |
| General web | SearXNG search | Any web mentions |

### Temporal Context (Loom Bridge)

| Source | Method | Data |
|--------|--------|------|
| Loom DB (71GB SQLite) | Read-only SQLite query | Historical events matching person/company names |

---

## Infrastructure

| Service | Purpose | Image |
|---------|---------|-------|
| SearXNG | Metasearch engine (Google, Bing, DDG) | searxng/searxng |
| Crawl4AI | JS-rendered web scraping | unclecode/crawl4ai |
| vLLM | Local LLM inference (Qwen3.5) | vllm/vllm-openai |
| HiveMindDB | Knowledge graph + vector DB | hiveminddb |
| Tor Proxy | SOCKS5 proxy for .onion access | dperson/torproxy |
