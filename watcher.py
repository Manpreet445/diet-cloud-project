"""
watcher.py
Simulates an event-driven trigger (Azurite has no real triggers).
Watches the ./trigger folder; when a new .csv lands, it re-runs the function.

Run:  pip install watchdog
      python3 watcher.py
Then in a SECOND terminal:  cp All_Diets.csv trigger/run1.csv
"""
import time, os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from lambda_function import process_nutritional_data_from_azurite


class TriggerHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith(".csv"):
            print(f"\nNew file detected: {event.src_path} -> running function")
            process_nutritional_data_from_azurite()


if __name__ == "__main__":
    os.makedirs("trigger", exist_ok=True)
    print("Watching ./trigger for new CSV files... (Ctrl+C to stop)")
    obs = Observer()
    obs.schedule(TriggerHandler(), "trigger", recursive=False)
    obs.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()
