from datetime import date, timedelta
from csv import DictWriter

COLUMNS = ("number", "issued_on", "amount_minor", "currency", "buyer_email")

def build_csv(request, ledger, out):
    actor = request.actor
    if not actor.is_authenticated:
        raise PermissionError("login required")
    start = date.fromisoformat(request.query["from"])
    finish = date.fromisoformat(request.query["to"])
    if finish < start:
        raise ValueError("invalid date order")
    if (finish - start).days > 30:
        raise ValueError("window too large")
    rows = ledger.find(
        account_id=actor.account_id,
        start=start,
        end=finish,
        status="open",
    )
    writer = DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row[name] for name in COLUMNS})

def suggested_start(today):
    return today - timedelta(days=30)
