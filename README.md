# PaperPulse

PaperPulse is a GitHub Actions + GitHub Pages paper monitor. It collects recent papers from multiple sources, filters them by your research interests, enriches them with an OpenAI-compatible LLM, and publishes a searchable daily reading page.

The default configuration is tuned for robotics, embodied AI, VLA, robot learning, and EEG/BCI-based control, but the source queries and keywords are plain YAML and can be changed for any research area.

## Features

- Multi-source collection from arXiv, Semantic Scholar, Crossref, and Google Scholar fallback query links.
- AI-generated summaries through OpenAI-compatible APIs, including Zhipu GLM Coding Plan.
- GitHub-native deployment with no server: GitHub Actions produces data, GitHub Pages serves the UI.
- Daily scheduled runs plus manual workflow dispatch.
- Keyword and author highlighting in the browser.
- Date filtering, category filtering, search, and statistics pages.
- Data branch publishing, so generated JSONL files do not clutter the main branch.

## How It Works

1. GitHub Actions runs `.github/workflows/run.yml` every day.
2. `daily_arxiv/collect_papers.py` collects candidate papers from configured sources.
3. `daily_arxiv/daily_arxiv/check_stats.py` removes papers already seen in recent days.
4. `ai/enhance.py` calls your configured LLM and writes structured summaries.
5. `to_md/convert.py` generates Markdown, while the web UI reads JSONL data directly.
6. The workflow pushes generated data to the `data` branch.
7. GitHub Pages serves the static app from `main`, and the app reads data from the `data` branch.

## Sources

Configure sources in `daily_arxiv/config.yaml`.

- `arxiv`: recent papers by arXiv category.
- `semantic_scholar`: query-based metadata search.
- `crossref`: DOI and publisher metadata discovery.
- `google_scholar`: fallback query links written to `data/<date>_scholar_queries.txt`.

Google Scholar is intentionally used as a discovery fallback, not as an automated scraper.

## GitHub Deployment

Create a GitHub repository, for example:

```text
paperpulse
```

Push this project to it:

```bash
git add .
git commit -m "setup PaperPulse"
git branch -M main
git remote add origin https://github.com/<your-username>/paperpulse.git
git push -u origin main
```

In your GitHub repository, open:

```text
Settings -> Actions -> General -> Workflow permissions
```

Select:

```text
Read and write permissions
```

Then open:

```text
Settings -> Secrets and variables -> Actions
```

Add these Secrets:

```text
OPENAI_API_KEY = your Zhipu API key
OPENAI_BASE_URL = https://open.bigmodel.cn/api/coding/paas/v4
```

Optional Secrets:

```text
ACCESS_PASSWORD = password for the public web page
TOKEN_GITHUB = GitHub token for higher API limits when checking code links
```

Add these Variables:

```text
MODEL_NAME = GLM-4.7
LANGUAGE = Chinese
CATEGORIES = cs.RO, cs.AI, cs.CV, cs.LG, cs.CL, eess.SP, q-bio.NC
EMAIL = your GitHub email
NAME = your GitHub name
```

Enable GitHub Pages:

```text
Settings -> Pages
Source: Deploy from a branch
Branch: main
Folder: / (root)
```

Run it once manually:

```text
Actions -> daily-paper-ai-enhanced -> Run workflow
```

Your page will be available at:

```text
https://<your-username>.github.io/<repo-name>/
```

## Daily Schedule

The default schedule in `.github/workflows/run.yml` is:

```yaml
schedule:
  - cron: "30 1 * * *"
```

GitHub cron uses UTC. This runs at 09:30 China time. For 08:00 China time, use:

```yaml
schedule:
  - cron: "0 0 * * *"
```

## Local Run

Install dependencies:

```bash
uv sync
```

Set environment variables:

```bash
export OPENAI_API_KEY="your-api-key"
export OPENAI_BASE_URL="https://open.bigmodel.cn/api/coding/paas/v4"
export MODEL_NAME="GLM-4.7"
export LANGUAGE="Chinese"
```

Run:

```bash
bash run.sh
```

On Windows, use Git Bash or WSL for `run.sh`.

## Customizing Topics

Edit `daily_arxiv/config.yaml`.

Common changes:

- Add or remove arXiv categories under `sources.arxiv.categories`.
- Add Semantic Scholar or Crossref queries under their `queries` lists.
- Change `keywords.high_priority` and `keywords.include` to tune filtering.
- Disable a source with `enabled: false`.

The collector writes both legacy fields used by the existing front end and richer metadata:

```text
source, venue, doi, arxiv_id, keywords_matched, research_direction, priority, links
```

## Zhipu GLM Coding Plan

PaperPulse uses `langchain-openai`, so Zhipu's OpenAI-compatible endpoint works through the usual OpenAI-style environment variables:

```text
OPENAI_API_KEY = your Zhipu API key
OPENAI_BASE_URL = https://open.bigmodel.cn/api/coding/paas/v4
MODEL_NAME = GLM-4.7
```

If your selected model or endpoint does not support structured tool/function output, `ai/enhance.py` is the place to add a JSON-prompt fallback.

## Notes

- Respect each source's terms of service and robots policy.
- Publisher pages may be incomplete or paywalled; use DOI, arXiv, author pages, and institutional repositories for verification.
- Google Scholar fallback links are intended for discovery and manual verification.
- The default third-party sensitive-content check is disabled. Set `ENABLE_SENSITIVE_CHECK=true` only if you intentionally want to use that external service.

## License

This project keeps the upstream Apache-2.0 license. See `LICENSE`.
