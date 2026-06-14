"""
lambda_function.py
Simulated Azure serverless function (Task 3).
Reads All_Diets.csv from the Azurite Blob emulator, computes the average
protein/carbs/fat per diet type, and writes the result to a simulated NoSQL
store (simulated_nosql/results.json).

Run Azurite, run upload_to_azurite.py once, then: python3 lambda_function.py
"""
from azure.storage.blob import BlobServiceClient
import pandas as pd
import io, json, os

CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
    "K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)
CONTAINER = "datasets"
BLOB_NAME = "All_Diets.csv"


def find_col(df, keyword):
    """Find a column by keyword (handles 'Protein(g)' vs 'Protein (g)')."""
    for c in df.columns:
        if keyword.lower() in c.lower():
            return c
    raise KeyError(f"No column for '{keyword}'. Columns are: {list(df.columns)}")


def process_nutritional_data_from_azurite():
    # 1. Connect to Azurite and download the blob
    svc = BlobServiceClient.from_connection_string(CONN_STR)
    blob = svc.get_blob_client(CONTAINER, BLOB_NAME)
    stream = blob.download_blob().readall()
    df = pd.read_csv(io.BytesIO(stream))

    # 2. Identify columns + clean
    diet = find_col(df, "diet")
    protein, carbs, fat = find_col(df, "protein"), find_col(df, "carb"), find_col(df, "fat")
    for col in [protein, carbs, fat]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df[diet] = df[diet].astype(str).str.strip().str.title()
    df[[protein, carbs, fat]] = df[[protein, carbs, fat]].fillna(
        df[[protein, carbs, fat]].mean()
    )

    # 3. Compute averages per diet type
    avg = df.groupby(diet)[[protein, carbs, fat]].mean().round(2)

    # 4. Save to simulated NoSQL store (JSON document store)
    os.makedirs("simulated_nosql", exist_ok=True)
    result = avg.reset_index().to_dict(orient="records")
    with open("simulated_nosql/results.json", "w") as f:
        json.dump(result, f, indent=2)

    print("Average macronutrients per diet type:\n", avg)
    print("\nSaved -> simulated_nosql/results.json")
    return "Data processed and stored successfully."


if __name__ == "__main__":
    print(process_nutritional_data_from_azurite())
