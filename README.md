# Dullknife

A member directory and collaboration hub for the Wyoming developer community. Built for US developers — especially Wyoming residents and expatriates — to connect, showcase their skills, and find each other.

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green) ![MariaDB](https://img.shields.io/badge/MariaDB-11.4-orange) ![Platform](https://img.shields.io/badge/Platform-FreeBSD%2014.x-red)

**Live at:** [https://www.dullknife.com](https://www.dullknife.com)

## What It Does

Dullknife is a public-facing web application where Wyoming-connected developers can:

- **Browse the member directory** — filter by discipline, search by skills or city, paginated results with profile photos
- **Apply for membership** — public application form with reCAPTCHA, admin review workflow
- **Maintain a profile** — skills summary, disciplines, profile photo, location with Wyoming-specific cascading city/ZIP dropdowns
- **Contact other members** — visitor-to-member contact form (email forwarded, no addresses exposed)
- **Advertise** — members can submit banner ads for admin approval

Admins get a full management panel: approve/reject applicants, edit members, send group emails, manage advertising.

## Tech Stack

| Component | Technology |
|---|---|
| Backend | Python / FastAPI with Jinja2 templates |
| Database | MariaDB 11.4 |
| Auth | bcrypt password hashing, cookie-based sessions |
| Email | Postfix (localhost SMTP, no auth) with DKIM signing |
| Image Processing | Pillow (400x400px profile photos, 300x100px ad banners) |
| Bot Protection | Google reCAPTCHA v2 Invisible |
| Reverse Proxy | Apache 2.4 with SSL (Let's Encrypt) |
| Server OS | FreeBSD 14.x |

### Python Dependencies

`fastapi` `uvicorn` `PyMySQL` `bcrypt` `python-multipart` `jinja2` `Pillow`

## Architecture

```
dullknife_rev1/
├── main.py                 # FastAPI app, landing page (featured members + ads)
├── database.py             # PyMySQL connection pool (DictCursor)
├── routers/
│   ├── auth.py             # Login, logout, member page, password reset, image upload
│   ├── admin.py            # Admin panel, user management, group email, advertising
│   ├── directory.py        # Member directory with discipline filter and search
│   ├── membership.py       # Membership application form
│   └── pages.py            # About, Contact Us, Contact Member, ZIP code API
├── utils/
│   └── email.py            # All email functions (reset, approval, rejection, group, contact)
├── templates/              # 24 Jinja2 templates
│   ├── landing.html        # Homepage — featured members + ad strip
│   ├── directory.html      # Searchable, filterable member directory
│   ├── member.html         # Member profile editor (view/edit toggle)
│   ├── member_profile.html # Public profile page
│   ├── admin_*.html        # Admin panel templates (7 files)
│   └── ...                 # Login, apply, contact, password reset, etc.
└── static/
    ├── css/style.css       # Single stylesheet — responsive (900px/600px breakpoints)
    ├── images/             # Member photos ({id}/{hex}.ext) and ad banners (ads/)
    └── favicon.ico
```

### Routes

| Router | Prefix | Key Routes |
|---|---|---|
| `auth.py` | — | `/login`, `/logout`, `/member`, `/reset-password`, `/change-password`, `/member/upload-image`, `/request-ad` |
| `admin.py` | `/admin` | `/admin/login`, `/admin/panel`, `/admin/manage-users`, `/admin/edit-user/{id}`, `/admin/advertising/*` |
| `directory.py` | `/directory` | `/directory` (GET with search/filter/pagination) |
| `membership.py` | `/apply` | `/apply` (GET/POST) |
| `pages.py` | — | `/about`, `/contact`, `/contact/{member_id}`, `/api/wyoming-zipcodes/{city}` |

### Database Schema

12 tables in MariaDB:

| Table | Purpose |
|---|---|
| `members` | Member profiles, credentials, status (`applicant` → `current` → `banned`) |
| `admins` | Admin accounts with separate session/lockout logic |
| `disciplines` | 7 developer discipline categories |
| `member_disciplines` | Junction table (members ↔ disciplines) |
| `member_images` | Multiple photos per member, `is_active` flag, 400x400px |
| `advertisers` | Ad banners with approval workflow (`pending`/`active`/`inactive`/`rejected`) |
| `password_reset_tokens` | Time-limited tokens (20min TTL) |
| `contact_submissions` | Visitor → member contact form entries |
| `contact_us_submissions` | Visitor → admin contact form entries |
| `wyoming_cities` | 93 Wyoming cities (for cascading dropdowns) |
| `wyoming_zipcodes` | 103 city/ZIP mappings |
| `countries` | 194 countries |

## Key Flows

### New Member Lifecycle

```
Visitor applies (/apply)
  → reCAPTCHA verified
  → Record created as member_type='applicant'
  → Admin notified via email
  → Admin approves in panel
  → member_type='current', password_hash='temporary'
  → Approval email sent to applicant
  → Member logs in with password 'temporary'
  → Forced redirect to password change
  → Full access granted
```

### Authentication

- Login with reCAPTCHA verification (skippable via "private computer" cookie)
- bcrypt password verification (temporary password checked BEFORE bcrypt to avoid salt error)
- 3 failed attempts → warning displayed
- 5 failed attempts → 1-hour lockout
- Separate admin auth with its own session cookie and lockout logic

### Password Reset

- Request via `/reset-password` → emailed link with 20-minute token
- Token is single-use (marked `used` after consumption)
- New password must differ from current password

### Cascading Dropdowns

When a user selects Wyoming as their state, the city field switches from a text input to a dropdown of 93 Wyoming cities. Selecting a city triggers an API call (`/api/wyoming-zipcodes/{city}`) that populates the ZIP code dropdown. Non-Wyoming states and non-US countries fall back to free-text inputs. Implemented on both the application form and member profile editor.

## Email

All outbound email flows through Postfix on localhost:25 (no authentication required). DKIM-signed via OpenDKIM.

| Flow | Trigger | Recipient |
|---|---|---|
| Password reset link | Member requests reset | Member's email |
| Application received | New application submitted | Admin |
| Approval notification | Admin approves applicant | New member's email |
| Rejection notification | Admin rejects applicant | Applicant's email |
| Contact Us | Visitor fills contact form | Admin |
| Contact Member | Visitor contacts a member | Member's email |
| Group email | Admin sends broadcast | All current members (individually) |

## Deployment

The application runs on a FreeBSD 14.x server behind Apache 2.4 (SSL termination via Let's Encrypt).

```bash
# Start the application (auto-reloads on file changes)
cd /var/www/pyengines/dullknife_rev1
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Apache reverse-proxies HTTPS traffic to uvicorn on port 8000.

### Required Services

- **MariaDB** — database backend
- **Postfix** — outbound email (localhost:25)
- **OpenDKIM** — DKIM signing for outbound mail
- **Apache 2.4** — reverse proxy with SSL

## Screenshots

*Coming soon*

## License

MIT
