from pathlib import PurePath

MAX_BYTES = 10 * 1024 * 1024
EXTENSIONS = {".pdf", ".zip"}

def upload(request, blobs, records):
    body = request.stream.read()
    name = request.headers["X-Filename"]
    if PurePath(name).suffix.lower() not in EXTENSIONS:
        return {"error": "unsupported"}, 415
    if len(body) > MAX_BYTES:
        return {"error": "too_large"}, 413
    object_id = blobs.put(body)
    record = records.insert(
        workspace=request.workspace.id,
        filename=name,
        object_id=object_id,
    )
    return {"id": record.id}, 201

def display_size(byte_count):
    return f"{byte_count / 1024:.0f} KiB"

def visible_name(record):
    return PurePath(record.filename).name
