import uuid

def deliver(job, http, queue, store):
    hook = store.get_hook(job.hook_id)
    response = http.post(
        hook.url,
        json=job.payload,
        headers={"X-Event-Id": str(uuid.uuid4())},
        timeout=10,
    )
    if response.status >= 500:
        queue.enqueue(job, delay=60)
    elif response.status >= 400:
        store.mark_failed(job.id, response.status)
    else:
        store.mark_delivered(job.id)

def compact_result(response):
    return {"status": response.status, "bytes": len(response.body)}

def remove_hook(hook_id, store):
    store.disable_hook(hook_id)

def list_hooks(account_id, store):
    return store.for_account(account_id)
