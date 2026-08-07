# QueueLess Nepal

Smart Queue Management SaaS Platform — Django + PostgreSQL, mobile-first UI.

## Environment

- Virtual environment: `D:\venvs\qless_venv` (Python 3.13, kept off the project's C: drive)
- PostgreSQL 17: installed at `D:\PostgreSQL\17`, data directory `D:\PostgreSQL\17\data`, service `postgresql-x64-17` on port 5432
- Database: `queueless_nepal_db`, owned by role `queueless_admin` (credentials in `.env`, not committed)

## Setup (already done for this environment)

```bash
D:\venvs\qless_venv\Scripts\python.exe -m pip install -r requirements.txt
D:\venvs\qless_venv\Scripts\python.exe manage.py migrate
D:\venvs\qless_venv\Scripts\python.exe manage.py createsuperuser
```

## Run the dev server

```bash
D:\venvs\qless_venv\Scripts\python.exe manage.py runserver
```

Visit http://127.0.0.1:8000/ and http://127.0.0.1:8000/admin/.

## Apps

| App | Purpose |
|---|---|
| `core` | Shared base templates, home page, common utilities |
| `accounts` | Custom user model, authentication, RBAC (customer / org admin / staff / super admin) |
| `organizations` | Organization profiles, departments, working hours |
| `customers` | Customer-facing profile and preferences |
| `staff` | Staff profiles and staff dashboard |
| `queue_management` | Token/queue engine (named `queue_management` — `queue` collides with the Python stdlib module) |
| `services` | Services offered by organizations |
| `notifications` | In-app/SMS/email notifications |
| `reports` | Analytics and PDF/CSV reporting |
| `subscriptions` | SaaS subscription plans and billing cycles |
| `payments` | Payment processing and transaction records |
| `dashboard` | Role-based dashboard routing and KPIs |

## Design system

Tokens live in `static/css/tokens.css` (colors, typography, spacing, radius) and the mobile-first
shell (sticky header, sidebar on desktop, bottom navigation on mobile, FAB) is in `static/css/base.css`.
Base layout: `templates/base.html`.
