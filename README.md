# diet-cloud-project

Serverless nutrition analytics on Azure. A **Blob Trigger** cleans the diet dataset the moment it
changes, writes a cleaned copy back to storage, computes every chart aggregation, and pushes the
result into **Azure Cache for Redis**. The HTTP endpoints serve that cached JSON, so the dashboard
never waits on a CSV parse.

```
uploads/All_Diets.csv  ──trigger──▶  clean_and_cache()  ──▶  processed/Cleaned_Diets.csv
                                            │
                                            ▼
                                  Redis: diet:insights:latest
                                            │
                       /api/insights · /api/clusters ──▶  index.html dashboard
```

## Storage layout

| Container   | Blob                | Role                                          |
|-------------|---------------------|-----------------------------------------------|
| `uploads`   | `All_Diets.csv`     | Input. The trigger watches this exact path.   |
| `processed` | `Cleaned_Diets.csv` | Output. Separate container, so no re-trigger. |

## Settings

Set these as Function App *Environment variables* in Azure, and in `local.settings.json` locally
(that file is gitignored — never commit a connection string).

| Setting | Purpose |
|---|---|
| `AzureWebJobsStorage` | Storage account connection string (`UseDevelopmentStorage=true` for Azurite) |
| `INPUT_CONTAINER` / `INPUT_BLOB` | Defaults `uploads` / `All_Diets.csv` |
| `CLEAN_CONTAINER` / `CLEAN_BLOB` | Defaults `processed` / `Cleaned_Diets.csv` |
| `REDIS_URL` | `rediss://:<primary-key>@<name>.redis.cache.windows.net:6380/0` in Azure, `redis://localhost:6379/0` locally |
| `CACHE_KEY` | Default `diet:insights:latest` |
| `CACHE_TTL_SECONDS` | Default `86400` (24h) |

If `REDIS_URL` is missing or Redis is unreachable, the endpoints fall back to reading the blob —
slower, but nothing breaks.

## Run it locally

```bash
docker run -d -p 6379:6379 --name diet-redis redis   # cache
npx azurite                                          # storage emulator
pip install -r requirements.txt
python upload_to_azurite.py                          # creates containers + uploads the CSV
func start                                           # trigger fires
```

Check the result:

```bash
docker exec -it diet-redis redis-cli GET diet:insights:latest
curl "http://localhost:7071/api/insights"            # look for "source": "cache"
```

Re-running `python upload_to_azurite.py` overwrites the blob and fires the trigger again.

## API

| Endpoint | Returns | Served from |
|---|---|---|
| `GET /api/insights` | `avg_macros`, `distribution`, `total_recipes` | Redis (blob fallback) |
| `GET /api/clusters` | `correlation_matrix`, `diet_stats` | Redis (blob fallback) |
| `GET /api/recipes?limit=N` | Row-level recipe list | `processed/Cleaned_Diets.csv` |

Every response carries `"source"` so you can confirm a cache hit, and `execution_time_ms` to compare
cached against cold. `insights` and `clusters` also accept `?diet=keto`.

## Files

- `function_app.py` — the blob trigger, cleaning, aggregations, cache, and HTTP endpoints
- `index.html` — dashboard (Chart.js), deployed to Azure Static Web Apps
- `upload_to_azurite.py` — local container setup + CSV upload
- `data_analysis.py`, `lambda_function.py`, `watcher.py` — earlier phases, kept for reference
