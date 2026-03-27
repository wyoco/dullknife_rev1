from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from typing import Optional
# from passlib.context import CryptContext
import bcrypt
from database import get_db
import time

router = APIRouter()
templates = Jinja2Templates(directory="templates")
# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


LOCKOUT_ATTEMPTS = 5
LOCKOUT_DURATION = 3600
WARNING_AT = 3

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None, "warning": None})

@router.post("/login")
def login_submit(
    request: Request,
    response: Response,
    db=Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    suppress_recaptcha: Optional[str] = Form(None)
):
    with db.cursor() as cursor:
        cursor.execute("""
            SELECT id, username, password_hash, member_type, failed_attempts, lockout_until
            FROM members WHERE username = %s
        """, (username,))
        member = cursor.fetchone()

    if not member:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password.",
            "warning": None
        })

    if member["member_type"] == "banned":
        return RedirectResponse(url="/banned", status_code=303)

    now = time.time()
    if member["lockout_until"] and member["lockout_until"] > now:
        return RedirectResponse(url="/account-locked", status_code=303)

#    if not pwd_context.verify(password, member["password_hash"]):
    if not bcrypt.checkpw(password.encode(), member["password_hash"].encode()):

        new_attempts = member["failed_attempts"] + 1
        lockout_until = None
        if new_attempts >= LOCKOUT_ATTEMPTS:
            lockout_until = now + LOCKOUT_DURATION
        with db.cursor() as cursor:
            cursor.execute("""
                UPDATE members SET failed_attempts = %s, lockout_until = %s
                WHERE id = %s
            """, (new_attempts, lockout_until, member["id"]))
            db.commit()
        if new_attempts >= LOCKOUT_ATTEMPTS:
            return RedirectResponse(url="/account-locked", status_code=303)
        warning = None
        if new_attempts >= WARNING_AT:
            remaining = LOCKOUT_ATTEMPTS - new_attempts
            warning = f"WARNING: {new_attempts} failed login attempts detected. You have {remaining} more attempt(s) before this account is locked."
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid username or password.",
            "warning": warning
        })

    with db.cursor() as cursor:
        cursor.execute("""
            UPDATE members SET failed_attempts = 0, lockout_until = NULL
            WHERE id = %s
        """, (member["id"],))
        db.commit()

    if member["password_hash"] == "temporary":
        resp = RedirectResponse(url="/new-member-reset", status_code=303)
        resp.set_cookie("member_id", str(member["id"]), httponly=True)
        return resp

    resp = RedirectResponse(url="/member", status_code=303)
    resp.set_cookie("member_id", str(member["id"]), httponly=True)
    if suppress_recaptcha:
        resp.set_cookie("suppress_recaptcha", "1", httponly=True, max_age=31536000)
    return resp

@router.get("/member")                                                                                                           
def member_page(request: Request):
    return templates.TemplateResponse("member.html", {"request": request})

