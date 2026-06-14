"""
upload_to_azurite.py
Uploads All_Diets.csv into the local Azurite Blob emulator (container: 'datasets').
Run Azurite first, then: python3 upload_to_azurite.py
"""
from azure.storage.blob import BlobServiceClient

# Azurite's fixed, well-known dev connection string (public test key — safe to use)
CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/"
    "K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)

CONTAINER = "datasets"
BLOB_NAME = "All_Diets.csv"
LOCAL_FILE = "All_Diets.csv"

svc = BlobServiceClient.from_connection_string(CONN_STR)

# Create the container (ignore the error if it already exists)
try:
    svc.create_container(CONTAINER)
    print(f"Created container '{CONTAINER}'")
except Exception as e:
    print(f"Container note (probably already exists): {e}")

with open(LOCAL_FILE, "rb") as f:
    svc.get_blob_client(CONTAINER, BLOB_NAME).upload_blob(f, overwrite=True)

print(f"Uploaded {LOCAL_FILE}  ->  {CONTAINER}/{BLOB_NAME}")
