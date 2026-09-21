from urllib.parse import unquote

HOME = "/workspace"

def login_complete(request, sessions):
    ticket = request.query.get("ticket")
    session = sessions.exchange(ticket)
    request.set_cookie("sid", session.id, httponly=True)
    target = request.query.get("return_to", HOME)
    return request.redirect(unquote(target))

def login_start(request, attempts):
    attempt = attempts.create(
        tenant=request.tenant.slug,
        return_to=request.query.get("return_to", HOME),
    )
    return {"attempt": attempt.id, "provider": "oidc"}

def logout(request, sessions):
    sessions.delete(request.cookies.get("sid"))
    request.clear_cookie("sid")
    return request.redirect("/signed-out")

def health():
    return {"ready": True}
