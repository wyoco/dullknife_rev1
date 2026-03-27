from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from typing import Optional, List
import bcrypt
from database import get_db
import time

router = APIRouter()
templates = Jinja2Templates(directory="templates")

LOCKOUT_ATTEMPTS = 5
LOCKOUT_DURATION = 3600
WARNING_AT = 3

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

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
        return RedirectResponse(url="/login-failed", status_code=303)

    if member["member_type"] == "banned":
        return RedirectResponse(url="/banned", status_code=303)

    now = time.time()
    if member["lockout_until"] and member["lockout_until"] > now:
        return RedirectResponse(url="/account-locked", status_code=303)

    if member["password_hash"] == "temporary":
        if password != "temporary":
            return RedirectResponse(url="/login-failed", status_code=303)
        resp = RedirectResponse(url="/new-member-reset", status_code=303)
        resp.set_cookie("member_id", str(member["id"]), httponly=True)
        return resp

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
        return RedirectResponse(url=f"/login-failed?attempts={new_attempts}", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("""
            UPDATE members SET failed_attempts = 0, lockout_until = NULL
            WHERE id = %s
        """, (member["id"],))
        db.commit()

    resp = RedirectResponse(url="/member", status_code=303)
    resp.set_cookie("member_id", str(member["id"]), httponly=True)
    if suppress_recaptcha:
        resp.set_cookie("suppress_recaptcha", "1", httponly=True, max_age=31536000)
    return resp

@router.get("/login-failed")
def login_failed(request: Request, attempts: int = 0):
    warning = None
    if attempts >= WARNING_AT:
        remaining = LOCKOUT_ATTEMPTS - attempts
        warning = f"WARNING: {attempts} failed login attempts detected. You have {remaining} more attempt(s) before this account is locked."
    return templates.TemplateResponse("login_failed.html", {"request": request, "warning": warning})

@router.get("/member")
def member_page(request: Request, db=Depends(get_db)):
    member_id = request.cookies.get("member_id")
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM members WHERE id = %s", (member_id,))
        member = cursor.fetchone()

    if not member or member["member_type"] != "current":
        return RedirectResponse(url="/login", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("SELECT discipline_id FROM member_disciplines WHERE member_id = %s", (member_id,))
        member_disc_ids = {row["discipline_id"] for row in cursor.fetchall()}

    with db.cursor() as cursor:
        cursor.execute("SELECT id, name FROM disciplines ORDER BY name")
        all_disciplines = cursor.fetchall()

    disciplines = [{"id": d["id"], "name": d["name"], "checked": d["id"] in member_disc_ids} for d in all_disciplines]

    return templates.TemplateResponse("member.html", {
        "request": request,
        "member": member,
        "disciplines": disciplines
    })

@router.post("/member")
def member_update(
    request: Request,
    db=Depends(get_db),
    first_name: str = Form(...),
    middle_name: Optional[str] = Form(None),
    last_name: str = Form(...),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    zipcode: Optional[str] = Form(None),
    phone_1: Optional[str] = Form(None),
    phone_2: Optional[str] = Form(None),
    skills_summary: Optional[str] = Form(None),
    disciplines: Optional[List[str]] = Form(default=None),
):
    member_id = request.cookies.get("member_id")
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)

    with db.cursor() as cursor:
        cursor.execute("""
            UPDATE members SET first_name=%s, middle_name=%s, last_name=%s,
            address=%s, city=%s, state=%s, zipcode=%s, phone_1=%s, phone_2=%s, skills_summary=%s
            WHERE id=%s
        """, (first_name, middle_name, last_name, address, city, state, zipcode, phone_1, phone_2, skills_summary, member_id))

        cursor.execute("DELETE FROM member_disciplines WHERE member_id=%s", (member_id,))
        if disciplines:
            for disc_id in disciplines:
                cursor.execute(
                    "INSERT INTO member_disciplines (member_id, discipline_id) VALUES (%s, %s)",
                    (member_id, int(disc_id))
                )
        db.commit()

    return RedirectResponse(url="/member", status_code=303)

@router.get("/logout")
def logout(request: Request):
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("member_id")
    resp.delete_cookie("suppress_recaptcha")
    return resp

@router.get("/account-locked")
def account_locked(request: Request):
    return templates.TemplateResponse("account_locked.html", {"request": request})

@router.get("/banned")
def banned_account(request: Request):
    return templates.TemplateResponse("banned.html", {"request": request})

import secrets
import re
import datetime

def password_strength(password):
    if len(password) < 8:
        return "weak"
    score = sum([
        bool(re.search(r'[A-Z]', password)),
        bool(re.search(r'[a-z]', password)),
        bool(re.search(r'[0-9]', password)),
        bool(re.search(r'[^A-Za-z0-9]', password)),
    ])
    if score <= 1:
        return "weak"
    elif score <= 2:
        return "medium"
    return "hard"

@router.get("/reset-password")
def reset_password_page(request: Request):
    return templates.TemplateResponse("reset_password.html", {"request": request, "sent": False})

@router.post("/reset-password")
def reset_password_submit(request: Request, db=Depends(get_db), email: str = Form(...)):
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM members WHERE email = %s AND member_type = 'current'",
            (email,)
        )
        member = cursor.fetchone()

    if member:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.datetime.now() + datetime.timedelta(minutes=20)
        with db.cursor() as cursor:
            cursor.execute(
                "INSERT INTO password_reset_tokens (member_id, token, expires_at) VALUES (%s, %s, %s)",
                (member["id"], token, expires_at)
            )
            db.commit()
        reset_url = f"https://www.dullknife.com/change-password?token={token}"
        print(f"[PASSWORD RESET] {reset_url}", flush=True)
        # TODO: email reset_url to {email} when SMTP is configured

    return templates.TemplateResponse("reset_password.html", {"request": request, "sent": True})

@router.get("/change-password")
def change_password_page(request: Request, token: str = "", db=Depends(get_db)):
    if not token:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": "Invalid or missing reset token.", "success": False, "token": "", "form_error": None
        })
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id FROM password_reset_tokens WHERE token = %s AND used = 0 AND expires_at > NOW()",
            (token,)
        )
        record = cursor.fetchone()
    if not record:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": "This reset link is invalid or has expired.", "success": False, "token": "", "form_error": None
        })
    return templates.TemplateResponse("change_password.html", {
        "request": request, "error": None, "success": False, "token": token, "form_error": None
    })

@router.post("/change-password")
def change_password_submit(
    request: Request,
    db=Depends(get_db),
    token: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    with db.cursor() as cursor:
        cursor.execute(
            "SELECT id, member_id FROM password_reset_tokens WHERE token = %s AND used = 0 AND expires_at > NOW()",
            (token,)
        )
        record = cursor.fetchone()

    if not record:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": "This reset link is invalid or has expired.", "success": False, "token": "", "form_error": None
        })

    if password != confirm:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": None, "success": False, "token": token,
            "form_error": "Passwords do not match."
        })

    if password_strength(password) == "weak":
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": None, "success": False, "token": token,
            "form_error": "Password is too weak. Please use at least 8 characters with a mix of uppercase, lowercase, numbers, or symbols."
        })

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db.cursor() as cursor:
        cursor.execute("UPDATE members SET password_hash = %s WHERE id = %s", (hashed, record["member_id"]))
        cursor.execute("UPDATE password_reset_tokens SET used = 1 WHERE id = %s", (record["id"],))
        db.commit()

    return templates.TemplateResponse("change_password.html", {
        "request": request, "error": None, "success": True, "token": "", "form_error": None
    })

@router.get("/new-member-reset")
def new_member_reset(request: Request):
    member_id = request.cookies.get("member_id")
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("new_member_reset.html", {"request": request})

@router.get("/new-member-change-password")
def new_member_change_password(request: Request, db=Depends(get_db)):
    member_id = request.cookies.get("member_id")
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)
    with db.cursor() as cursor:
        cursor.execute("SELECT id FROM members WHERE id = %s AND password_hash = 'temporary'", (member_id,))
        member = cursor.fetchone()
    if not member:
        return RedirectResponse(url="/member", status_code=303)
    return templates.TemplateResponse("change_password.html", {
        "request": request, "error": None, "success": False, "token": None, "form_error": None, "new_member": True
    })

@router.post("/new-member-change-password")
def new_member_change_password_submit(
    request: Request,
    db=Depends(get_db),
    password: str = Form(...),
    confirm: str = Form(...),
):
    member_id = request.cookies.get("member_id")
    if not member_id:
        return RedirectResponse(url="/login", status_code=303)

    if password != confirm:
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": None, "success": False, "token": None,
            "form_error": "Passwords do not match.", "new_member": True
        })

    if password_strength(password) == "weak":
        return templates.TemplateResponse("change_password.html", {
            "request": request, "error": None, "success": False, "token": None,
            "form_error": "Password is too weak. Please use at least 8 characters with a mix of uppercase, lowercase, numbers, or symbols.",
            "new_member": True
        })

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db.cursor() as cursor:
        cursor.execute("UPDATE members SET password_hash = %s WHERE id = %s", (hashed, member_id))
        db.commit()

    return templates.TemplateResponse("change_password.html", {
        "request": request, "error": None, "success": True, "token": None, "form_error": None, "new_member": True
    })

@router.get("/new-member-cancel")
def new_member_cancel(request: Request):
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("member_id")
    return resp
