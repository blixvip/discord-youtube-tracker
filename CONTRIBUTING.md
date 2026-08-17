# Contributing

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
