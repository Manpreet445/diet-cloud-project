"""
Phase 2 - took the logic from lambda_function.py and put it into
a real Azure Function so we can actually deploy it and call it
"""

import azure.functions as func
import pandas as pd
from azure.storage.blob import BlobServiceClient
import io, json, os, time, logging

app = func.FunctionApp()

def find_col(df, keyword):
    for c in df.columns:
        if keyword.lower() in c.lower():
            return c
    raise KeyError(f"No column matching '{keyword}'. Columns: {list(df.columns)}")

def load_dataframe():
    # Grab the connection string and the container info from environment variables
    conn_str = os.environ["AzureWebJobsStorage"]
    container = os.environ.get("BLOB_CONTAINER", "diet-data")
    blob_name = os.environ.get("BLOB_NAME", "All_Diets.csv")

    # Connect to blob storage and download the CSV
    svc = BlobServiceClient.from_connection_string(conn_str)
    blob = svc.get_blob_client(container, blob_name)
    raw = blob.download_blob().readall()
    df = pd.read_csv(io.BytesIO(raw))

    # Figure out which columns are which
    diet = find_col(df, "diet")
    protein = find_col(df, "protein")
    carbs = find_col(df, "carb")
    fat = find_col(df, "fat")

    for col in [protein, carbs, fat]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        
    df[diet] = df[diet].astype(str).str.strip().str.title()
    df[[protein, carbs, fat]] = df[[protein, carbs, fat]].fillna(
        df[[protein, carbs, fat]].mean()
    )

    return df, diet, protein, carbs, fat


def make_response(body, status=200):
    return func.HttpResponse(
        json.dumps(body),
        status_code=status,
        mimetype="application/json",
    )

# Avg protein/carbs/fat per diet type, plus how many recipes each diet has
@app.route(route="insights", methods=["GET"])
def insights(req: func.HttpRequest) -> func.HttpResponse:
    start = time.time()
    try:
        df, diet, protein, carbs, fat = load_dataframe()

        diet_filter = req.params.get("diet")
        if diet_filter:
            df = df[df[diet].str.lower() == diet_filter.lower()]
            if df.empty:
                return make_response({"error": f"No data for diet '{diet_filter}'"}, 404)

        avg = df.groupby(diet)[[protein, carbs, fat]].mean().round(2)
        distribution = df[diet].value_counts().to_dict()

        return make_response({
            "avg_macros": avg.reset_index().rename(columns={
                diet: "diet_type",
                protein: "protein",
                carbs: "carbs",
                fat: "fat",
            }).to_dict(orient="records"),
            "distribution": distribution,
            "total_recipes": len(df),
            "execution_time_ms": round((time.time() - start) * 1000, 2),
        })
    except Exception as e:
        logging.exception("insights failed")
        return make_response({"error": str(e)}, 500)

# Top recipes sorted by protein, highest first
@app.route(route="recipes", methods=["GET"])
def recipes(req: func.HttpRequest) -> func.HttpResponse:
    start = time.time()
    try:
        df, diet, protein, carbs, fat = load_dataframe()
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
            "execution_time_ms": round((time.time() - start) * 1000, 2),
        })
    except Exception as e:
        logging.exception("recipes failed")
        return make_response({"error": str(e)}, 500)

# Correlation matrix between protein/carbs/fat for the heatmap
# Per-diet averages and most common cuisine per diet for the scatter plot
@app.route(route="clusters", methods=["GET"])
def clusters(req: func.HttpRequest) -> func.HttpResponse:
    start = time.time()
    try:
        df, diet, protein, carbs, fat = load_dataframe()
        cuisine = find_col(df, "cuisine")

        corr = df[[protein, carbs, fat]].corr().round(3)
        corr_clean = corr.rename(
            index={protein: "protein", carbs: "carbs", fat: "fat"},
            columns={protein: "protein", carbs: "carbs", fat: "fat"},
        )

        grouped = df.groupby(diet).agg(
            avg_protein=(protein, "mean"),
            avg_carbs=(carbs, "mean"),
            avg_fat=(fat, "mean"),
            recipe_count=(protein, "count"),
            top_cuisine=(cuisine, lambda x: x.mode().iloc[0] if not x.mode().empty else "N/A"),
        ).round(2).reset_index().rename(columns={diet: "diet_type"})

        return make_response({
            "correlation_matrix": {
                "labels": ["protein", "carbs", "fat"],
                "values": corr_clean.values.tolist(),
            },
            "diet_stats": grouped.to_dict(orient="records"),
            "execution_time_ms": round((time.time() - start) * 1000, 2),
        })
    except Exception as e:
        logging.exception("clusters failed")
        return make_response({"error": str(e)}, 500)