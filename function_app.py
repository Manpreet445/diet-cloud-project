"""
Phase 3 - event-driven pipeline.

A Blob Trigger fires whenever uploads/All_Diets.csv changes. That single run:
  1. cleans the data
  2. writes processed/Cleaned_Diets.csv back to storage
  3. computes every aggregation the dashboard needs
  4. pushes the result into Azure Cache for Redis

The HTTP endpoints then just read that cached JSON instead of re-parsing ~7,800
CSV rows on every single request like they used to.
"""

import azure.functions as func
import pandas as pd
from azure.storage.blob import BlobServiceClient
import io, json, os, time, logging
from datetime import datetime, timezone

app = func.FunctionApp()

# Where things live. Overridable via app settings / local.settings.json
INPUT_CONTAINER = os.environ.get("INPUT_CONTAINER", "uploads")
INPUT_BLOB = os.environ.get("INPUT_BLOB", "All_Diets.csv")
CLEAN_CONTAINER = os.environ.get("CLEAN_CONTAINER", "processed")
CLEAN_BLOB = os.environ.get("CLEAN_BLOB", "Cleaned_Diets.csv")
CACHE_KEY = os.environ.get("CACHE_KEY", "diet:insights:latest")
CACHE_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "86400"))  # 24h


# ---------------------------------------------------------------- helpers

def find_col(df, keyword):
    for c in df.columns:
        if keyword.lower() in c.lower():
            return c
    raise KeyError(f"No column matching '{keyword}'. Columns: {list(df.columns)}")


def blob_service():
    return BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])


def get_redis():
    """Return a Redis client, or None if it isn't configured/reachable.

    Returning None instead of raising means a missing cache degrades to the
    slow-but-correct blob path rather than taking the whole endpoint down.
    """
    url = os.environ.get("REDIS_URL")
    if not url:
        logging.warning("REDIS_URL not set - running without cache")
        return None
    try:
        import redis
        client = redis.from_url(url, decode_responses=True, socket_timeout=5)
        client.ping()
        return client
    except Exception as e:
        logging.warning(f"Redis unavailable ({e}) - falling back to blob")
        return None


# ---------------------------------------------------------------- step 2: cleaning

def clean_dataframe(df):
    """Clean the raw diet data. Returns (df, diet, protein, carbs, fat)."""
    rows_in = len(df)

    # Column headers sometimes carry stray whitespace ('Protein (g)' vs 'Protein(g)')
    df.columns = [str(c).strip() for c in df.columns]

    df = df.dropna(how="all")

    diet = find_col(df, "diet")
    protein = find_col(df, "protein")
    carbs = find_col(df, "carb")
    fat = find_col(df, "fat")
    macros = [protein, carbs, fat]

    # Anything non-numeric becomes NaN so we can fill it deliberately below
    for col in macros:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[df[col] < 0, col] = pd.NA   # negative grams is bad data, not a value
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Normalise the text columns so 'keto', ' Keto' and 'KETO' group together
    df[diet] = df[diet].astype(str).str.strip().str.title()
    try:
        cuisine = find_col(df, "cuisine")
        df[cuisine] = df[cuisine].astype(str).str.strip().str.title()
    except KeyError:
        pass

    # A row with no diet type or no name is useless to every chart
    df = df[df[diet].notna() & (df[diet].str.lower() != "nan") & (df[diet] != "")]
    try:
        recipe = find_col(df, "recipe")
        df = df[df[recipe].notna() & (df[recipe].astype(str).str.strip() != "")]
    except KeyError:
        pass

    df = df.drop_duplicates()

    # Fill missing macros with that diet type's own mean - closer to the truth
    # than one global mean across wildly different diets
    for col in macros:
        group_mean = df.groupby(diet)[col].transform("mean")
        df[col] = df[col].fillna(group_mean).fillna(df[col].mean()).fillna(0)

    df = df.reset_index(drop=True)
    logging.info(f"Cleaning: {rows_in} rows in -> {len(df)} rows out")

    return df, diet, protein, carbs, fat


def load_and_clean(container=None, blob_name=None):
    """Download a CSV from blob storage and clean it."""
    container = container or INPUT_CONTAINER
    blob_name = blob_name or INPUT_BLOB
    raw = blob_service().get_blob_client(container, blob_name).download_blob().readall()
    return clean_dataframe(pd.read_csv(io.BytesIO(raw)))


# ---------------------------------------------------------------- step 3: aggregations

def build_chart_payload(df, diet, protein, carbs, fat):
    """Everything the four dashboard charts need, as one JSON-ready dict."""
    avg = df.groupby(diet)[[protein, carbs, fat]].mean().round(2)
    counts = df[diet].value_counts()
    corr = df[[protein, carbs, fat]].corr().round(3)

    try:
        cuisine = find_col(df, "cuisine")
        top_cuisine = (cuisine, lambda x: x.mode().iloc[0] if not x.mode().empty else "N/A")
    except KeyError:
        top_cuisine = (protein, lambda x: "N/A")

    grouped = df.groupby(diet).agg(
        avg_protein=(protein, "mean"),
        avg_carbs=(carbs, "mean"),
        avg_fat=(fat, "mean"),
        recipe_count=(protein, "count"),
        top_cuisine=top_cuisine,
    ).round(2).reset_index().rename(columns={diet: "diet_type"})

    return {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_blob": f"{INPUT_CONTAINER}/{INPUT_BLOB}",
        "total_recipes": int(len(df)),

        # Bar chart - average macros per diet type
        "barChartData": {
            "labels": avg.index.tolist(),
            "protein": avg[protein].tolist(),
            "carbs": avg[carbs].tolist(),
            "fat": avg[fat].tolist(),
            "records": avg.reset_index().rename(columns={
                diet: "diet_type",
                protein: "protein",
                carbs: "carbs",
                fat: "fat",
            }).to_dict(orient="records"),
        },

        # Pie chart - how many recipes each diet type has
        "pieChartData": {
            "labels": counts.index.tolist(),
            "counts": [int(v) for v in counts.tolist()],
            "distribution": {k: int(v) for k, v in counts.to_dict().items()},
        },

        # Heatmap - correlation between the three macros
        "heatmapData": {
            "labels": ["protein", "carbs", "fat"],
            "values": corr.values.tolist(),
        },

        # Scatter - one point per diet type
        "scatterData": grouped.to_dict(orient="records"),
    }


def write_clean_csv(df):
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    svc = blob_service()
    try:
        svc.create_container(CLEAN_CONTAINER)
    except Exception:
        pass  # already exists
    svc.get_blob_client(CLEAN_CONTAINER, CLEAN_BLOB).upload_blob(csv_bytes, overwrite=True)
    logging.info(f"Wrote {CLEAN_CONTAINER}/{CLEAN_BLOB} ({len(csv_bytes)} bytes)")


def cache_payload(payload):
    r = get_redis()
    if r is None:
        return False
    r.set(CACHE_KEY, json.dumps(payload), ex=CACHE_TTL)
    logging.info(f"Cached payload under '{CACHE_KEY}' (ttl {CACHE_TTL}s)")
    return True


def read_cached_payload():
    r = get_redis()
    if r is None:
        return None
    try:
        cached = r.get(CACHE_KEY)
        return json.loads(cached) if cached else None
    except Exception as e:
        logging.warning(f"Cache read failed: {e}")
        return None


def get_payload():
    """Cached payload if we have one, otherwise rebuild from the blob and warm
    the cache on the way out. Returns (payload, source)."""
    cached = read_cached_payload()
    if cached:
        return cached, "cache"

    logging.info("Cache miss - rebuilding from blob")
    df, diet, protein, carbs, fat = load_and_clean()
    payload = build_chart_payload(df, diet, protein, carbs, fat)
    cache_payload(payload)
    return payload, "blob"


# ---------------------------------------------------------------- step 1: the trigger

def run_pipeline(csv_bytes, origin):
    """Clean -> write cleaned CSV -> aggregate -> cache. The whole job, once."""
    start = time.time()

    # Step 2 - read into memory, clean, write the cleaned copy back out
    df, diet, protein, carbs, fat = clean_dataframe(pd.read_csv(io.BytesIO(csv_bytes)))
    write_clean_csv(df)

    # Step 3 - aggregate straight from the dataframe we already have in memory
    payload = build_chart_payload(df, diet, protein, carbs, fat)

    # Step 4 - push it to the cache
    cached = cache_payload(payload)

    elapsed = round((time.time() - start) * 1000)
    logging.info(
        f"Pipeline ({origin}) done in {elapsed}ms - "
        f"{payload['total_recipes']} recipes, "
        f"{len(payload['barChartData']['labels'])} diet types, "
        f"cached={cached}"
    )
    return payload, cached, elapsed


# NOTE: this app runs on a Flex Consumption plan, which only supports the
# Event Grid based blob trigger - the older polling source never fires there.
# Storage needs an Event Grid subscription pointing at this function.
@app.blob_trigger(arg_name="inputblob",
                  path=f"{INPUT_CONTAINER}/{INPUT_BLOB}",
                  connection="AzureWebJobsStorage",
                  source=func.BlobSource.EVENT_GRID)
def clean_and_cache(inputblob: func.InputStream):
    """Fires when uploads/All_Diets.csv is created or overwritten."""
    logging.info(f"Blob trigger fired: {inputblob.name} ({inputblob.length} bytes)")
    try:
        run_pipeline(inputblob.read(), "blob trigger")
    except Exception:
        logging.exception("Blob trigger pipeline failed")
        raise  # let the Functions runtime record the failure and retry


# ---------------------------------------------------------------- HTTP endpoints

def make_response(body, status=200):
    return func.HttpResponse(
        json.dumps(body),
        status_code=status,
        mimetype="application/json",
    )


# Avg protein/carbs/fat per diet type, plus how many recipes each diet has
@app.route(route="insights", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def insights(req: func.HttpRequest) -> func.HttpResponse:
    start = time.time()
    try:
        payload, source = get_payload()
        avg_macros = payload["barChartData"]["records"]
        distribution = payload["pieChartData"]["distribution"]
        total = payload["total_recipes"]

        diet_filter = req.params.get("diet")
        if diet_filter:
            key = diet_filter.strip().lower()
            avg_macros = [r for r in avg_macros if str(r["diet_type"]).lower() == key]
            distribution = {k: v for k, v in distribution.items() if k.lower() == key}
            if not avg_macros:
                return make_response({"error": f"No data for diet '{diet_filter}'"}, 404)
            total = sum(distribution.values())

        return make_response({
            "avg_macros": avg_macros,
            "distribution": distribution,
            "total_recipes": total,
            "source": source,
            "generated_at": payload["generated_at"],
            "execution_time_ms": round((time.time() - start) * 1000, 2),
        })
    except Exception as e:
        logging.exception("insights failed")
        return make_response({"error": str(e)}, 500)


# Top recipes sorted by protein, highest first.
# Row-level data is too big to be worth caching, so this reads the cleaned CSV
# the trigger produced - already cleaned, so no re-cleaning needed.
@app.route(route="recipes", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def recipes(req: func.HttpRequest) -> func.HttpResponse:
    start = time.time()
    try:
        try:
            df, diet, protein, carbs, fat = load_and_clean(CLEAN_CONTAINER, CLEAN_BLOB)
            source = "cleaned-blob"
        except Exception:
            logging.warning("Cleaned CSV not available - falling back to raw input")
            df, diet, protein, carbs, fat = load_and_clean()
            source = "raw-blob"

        recipe = find_col(df, "recipe")
        cuisine = find_col(df, "cuisine")

        diet_filter = req.params.get("diet")
        if diet_filter:
            df = df[df[diet].str.lower() == diet_filter.lower()]
            if df.empty:
                return make_response({"error": f"No data for diet '{diet_filter}'"}, 404)

        limit = int(req.params.get("limit", 10))
        top = (
            df.sort_values(protein, ascending=False)
            .head(limit)[[diet, recipe, cuisine, protein, carbs, fat]]
            .rename(columns={
                diet: "diet_type",
                recipe: "recipe_name",
                cuisine: "cuisine_type",
                protein: "protein",
                carbs: "carbs",
                fat: "fat",
            })
        )

        return make_response({
            "recipes": top.to_dict(orient="records"),
            "count": len(top),
            "source": source,
            "execution_time_ms": round((time.time() - start) * 1000, 2),
        })
    except Exception as e:
        logging.exception("recipes failed")
        return make_response({"error": str(e)}, 500)


# Correlation matrix between protein/carbs/fat for the heatmap
# Per-diet averages and most common cuisine per diet for the scatter plot
@app.route(route="clusters", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def clusters(req: func.HttpRequest) -> func.HttpResponse:
    start = time.time()
    try:
        payload, source = get_payload()
        return make_response({
            "correlation_matrix": payload["heatmapData"],
            "diet_stats": payload["scatterData"],
            "source": source,
            "generated_at": payload["generated_at"],
            "execution_time_ms": round((time.time() - start) * 1000, 2),
        })
    except Exception as e:
        logging.exception("clusters failed")
        return make_response({"error": str(e)}, 500)


# Manual re-run of the same pipeline the blob trigger uses. Handy as a fallback
# if Event Grid delivery is slow, and for warming the cache after a deploy.
# Requires the function key - this is an admin action, not a public endpoint.
@app.route(route="refresh", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def refresh(req: func.HttpRequest) -> func.HttpResponse:
    try:
        raw = blob_service().get_blob_client(
            INPUT_CONTAINER, INPUT_BLOB).download_blob().readall()
        payload, cached, elapsed = run_pipeline(raw, "manual refresh")
        return make_response({
            "status": "ok",
            "cached": cached,
            "total_recipes": payload["total_recipes"],
            "generated_at": payload["generated_at"],
            "pipeline_ms": elapsed,
        })
    except Exception as e:
        logging.exception("refresh failed")
        return make_response({"error": str(e)}, 500)
