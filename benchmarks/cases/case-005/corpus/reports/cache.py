import json

def monthly_report(request, cache, reports):
    month = request.query["month"]
    key = f"report:{month}"
    cached = cache.get(key)
    if cached is not None:
        return json.loads(cached)
    data = reports.build(
        team=request.team.id,
        actor=request.actor,
        month=month,
    )
    cache.set(key, json.dumps(data), ttl=3600)
    return data

def label_month(month):
    year, number = month.split("-")
    return f"{year}/{number}"

def recent_months(calendar, count=6):
    return calendar.previous_months(count)

def empty_report():
    return {"rows": [], "total": 0}
