"""
upload_to_azurite.py
Sets up the local Azurite Blob emulator for the Phase 3 pipeline:
creates the 'uploads' and 'processed' containers, then uploads All_Diets.csv
into uploads/ - which is exactly what fires the blob trigger in function_app.py.

Run Azurite first, then: python upload_to_azurite.py
"""
from azure.storage.blob import BlobServiceClient

# Azurite's fixed, well-known dev connection string (public test key - safe to use)
CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
    "K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)

INPUT_CONTAINER = "uploads"      # blob trigger watches uploads/All_Diets.csv
CLEAN_CONTAINER = "processed"    # function writes Cleaned_Diets.csv here
BLOB_NAME = "All_Diets.csv"
LOCAL_FILE = "All_Diets.csv"

svc = BlobServiceClient.from_connection_string(CONN_STR)

for container in (INPUT_CONTAINER, CLEAN_CONTAINER):
    try:
        svc.create_container(container)
        print(f"Created container '{container}'")
    except Exception as e:
        print(f"Container '{container}' note (probably already exists): {e}")

with open(LOCAL_FILE, "rb") as f:
    svc.get_blob_client(INPUT_CONTAINER, BLOB_NAME).upload_blob(f, overwrite=True)

print(f"Uploaded {LOCAL_FILE}  ->  {INPUT_CONTAINER}/{BLOB_NAME}")
print("If 'func start' is running, the blob trigger should fire within a few seconds.")
