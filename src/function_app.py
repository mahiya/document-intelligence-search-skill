import json
import logging
import azure.functions as func
from utils.readdoc import get_ocr_file, parse_ocr_result
from utils.chunking import chunk_content


app = func.FunctionApp()


@app.route(route="skill", auth_level=func.AuthLevel.FUNCTION)
def SearchCustomSkill(req: func.HttpRequest) -> func.HttpResponse:
    body = req.get_json()
    logging.info(str(body))
    records = body["values"]
    resp = {"values": [process_record(record) for record in records]}
    return func.HttpResponse(json.dumps(resp, ensure_ascii=False), mimetype="application/json", status_code=200)


def process_record(record):
    storage_url = record["data"]["metadata_storage_path"] + record["data"]["metadata_storage_sas_token"]
    ocr_result = get_ocr_file(storage_url)
    content = parse_ocr_result(ocr_result)
    chunked_contents = chunk_content(content)
    output = [{"content": c} for c in chunked_contents]
    return {"recordId": record["recordId"], "data": {"output": output}}
