# Contributing

> 💬 **Before you open a PR, join the [blix open source Discord](https://discord.gg/wJfHQXfEMM).** It's the home for contributors across every blixvip repo: ask questions, run ideas by us, and talk through your PR.

Open an issue before a large behavioral change. Keep credentials, Discord IDs, subscription state, generated transcripts, and Worker state out of commits.

## Local checks

```bash
python -m pip install -r requirements.txt
python -m pytest -q
cd cloudflare
npm ci
npm run check
npm test
```

Pull requests should explain the user-visible change, cover failure paths, and include tests. Caption fixtures must be synthetic or short metadata samples; do not commit copied transcripts.
