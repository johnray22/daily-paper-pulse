# PaperPulse

PaperPulse is a GitHub Actions + GitHub Pages paper monitor. It collects recent papers from multiple sources, filters them by your research interests, enriches them with an OpenAI-compatible LLM, and publishes a searchable daily reading page.

## Setup

Configure sources in `daily_arxiv/config.yaml`, set GitHub Actions Secrets and Variables, enable GitHub Pages from the `main` branch root, and run the `daily-paper-ai-enhanced` workflow once.

Required Secrets:

```text
OPENAI_API_KEY
OPENAI_BASE_URL
```

For Zhipu GLM Coding Plan:

```text
OPENAI_BASE_URL = https://open.bigmodel.cn/api/coding/paas/v4
MODEL_NAME = GLM-4.7
```

## Content

{readme_content}
