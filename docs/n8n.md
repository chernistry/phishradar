# n8n — Export/Import and Environment Separation

This project stores n8n flow definitions in Git (`phishradar/n8n/flows/phishradar.json`).

## Export from Running Container
- Bring up the stack: `./scripts/run.sh dev up`
- Export all active flows to the mounted folder:
  - `./scripts/run.sh n8n export`
  - Results: files will appear in `phishradar/n8n/flows/exported/`

## Import to Container
- Ensure the required JSON file is in `phishradar/n8n/flows/phishradar.json`.
- Execute: `./scripts/run.sh n8n import`
- The `--overwrite` flag will overwrite existing flows with the same IDs.

## Secrets and Environments
- Do not hardcode tokens in nodes. Use expressions like `{{$env.VAR_NAME}}`.
- Set environment variable values through `.env`/Compose for different environments (dev/stage/prod).

## Publication Flow
1) Modify flows on the staging n8n instance.
2) Export (`n8n export`), commit JSON to Git.
3) Import to prod instance via `n8n import` (or CI).
