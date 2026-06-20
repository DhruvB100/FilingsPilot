"""
Azure Function (timer trigger): once a day check EDGAR for new annual filings.
New filing -> raw html to blob storage -> chunk -> embed -> postgres, and refresh the financials table.
The deploy script copies ../backend and ../sql next to this file.
"""
import os
import glob
import logging
import azure.functions as func

app = func.FunctionApp()


def upload_raw_files(folder):
    from azure.storage.blob import BlobServiceClient
    conn = os.getenv("RAW_BLOB_CONNECTION")
    if not conn:
        return
    container = BlobServiceClient.from_connection_string(conn).get_container_client(os.getenv("RAW_BLOB_CONTAINER", "raw-filings"))
    for path in glob.glob(os.path.join(folder, "**", "*.*"), recursive=True):
        name = os.path.relpath(path, folder).replace("\\", "/")
        with open(path, "rb") as f:
            container.upload_blob(name, f, overwrite=True)
        logging.info("uploaded %s", name)


# 12:00 UTC every day (6am Calgary)
@app.timer_trigger(schedule="0 0 12 * * *", arg_name="timer", run_on_startup=False)
def daily_filings_check(timer: func.TimerRequest) -> None:
    from backend import config, edgar, chunker, index_filings, load_facts
    from backend.db import get_conn

    conn = get_conn()
    known = {row[0] for row in conn.execute("SELECT accession FROM filings").fetchall()}
    logging.info("%d filings already indexed", len(known))

    new = edgar.run(known_accessions=known)
    if not new:
        logging.info("no new filings today")
        return

    logging.info("new filings: %s", new)
    upload_raw_files(config.RAW_DIR)
    chunker.run()
    index_filings.run()
    load_facts.run()
    logging.info("done indexing %d new filings", len(new))
