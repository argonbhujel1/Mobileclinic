# Mobile Clinic

**Second-hand smartphone marketplace & mobile repair platform**  
Owned by **Bishal Niraula** · Domain: [arganbhujel.info.np](https://arganbhujel.info.np)

Technology by [BAM Studio](https://bamstudio.argan.com.np/)

---

## Stack

| Layer | Technology |
|-------|------------|
| Backend | Python Flask + Jinja2 |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Database | Turso (libSQL) |
| Images | Cloudinary + ImgBB URL import |
| Maps | OpenStreetMap + Leaflet.js |
| Email | SMTP (Flask-Mail) |
| Deploy | GitHub → Vercel |

**No React, Next.js, Vue, Angular, Tailwind, or Bootstrap.**

---

## Features

- **Marketplace**: Admin & Seller listings (19 fields), guest checkout, cart, COD/QR
- **Seller system**: Application → delayed credential email → commission (8%) → Pay Admin via QR
- **Repairs**: Booking with map pickup, ticket tracking, staff GPS updates, live Admin map
- **Roles**: Admin, Customer, Seller, Staff — enforced in backend
- **Images**: File picker + ImgBB import → Cloudinary → Turso metadata
- **Customization**: Admin can change site name, colors, contact, etc. without redeploy
- **Security**: CSRF, hashed passwords, OTP, rate limits, SSRF protection, secure tracking tokens
- **Footer**: Permanent “Technology by BAM Studio” credit

---

## Quick Start (Local)

```bash
# 1. Clone & enter
git clone <your-repo>
cd mobile-clinic

# 2. Virtualenv
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 3. Install
pip install -r requirements.txt

# 4. Environment
cp .env.example .env
# Edit .env — at minimum set FLASK_SECRET_KEY.
# For full features add Turso, Cloudinary, SMTP credentials.

# 5. Seed admin
python scripts/seed_admin.py

# 6. Run
python wsgi.py
# → http://localhost:5000
```

Without Turso credentials the app falls back to a local `mobile_clinic.db` SQLite file.

---

## Environment Variables

See `.env.example` for the full list. Critical ones:

- `FLASK_SECRET_KEY`
- `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN`
- `CLOUDINARY_CLOUD_NAME` / `API_KEY` / `API_SECRET`
- `MAIL_SERVER` / `MAIL_USERNAME` / `MAIL_PASSWORD`
- `APP_BASE_URL`

---

## Background Worker

Seller credentials (2-minute delay) and commission deadline processing:

```bash
python scripts/worker.py
```

**Vercel note:** Serverless does not support long-running processes. Use an external cron that hits a secured API endpoint, or run the worker on a small VPS / Railway / Render process.

---

## Deployment (GitHub → Vercel → Domain)

1. Push this repository to GitHub.
2. Import project in [Vercel](https://vercel.com).
3. Set environment variables in Vercel dashboard.
4. Deploy. Framework preset: Other / Python.
5. Add custom domain `arganbhujel.info.np` and configure DNS as instructed by Vercel.

Verify current Vercel Python runtime support and request limits for your plan. For GPS ingestion and scheduled jobs, pair with an external worker.

---

## Default Admin

After `scripts/seed_admin.py`:

- Email: `bishal2014nir@gmail.com` (or `ADMIN_EMAIL`)
- Password: set via `ADMIN_PASSWORD` or default `ChangeMeAdmin123!`  
**Change the password immediately.**

---

## Project Structure

```
mobile-clinic/
├── app/
│   ├── blueprints/     # main, auth, marketplace, repair, dashboard, admin, api
│   ├── models/
│   ├── services/       # email, image, commission, settings
│   ├── templates/      # Jinja2 layouts, pages, dashboards, emails
│   ├── static/         # css, js
│   ├── utils/
│   ├── config.py
│   ├── db.py           # Turso/libSQL layer + schema
│   └── extensions.py
├── scripts/            # worker.py, seed_admin.py
├── wsgi.py
├── requirements.txt
├── vercel.json
├── .env.example
└── README.md
```

---

## Testing Checklist (manual)

- [ ] Register + OTP email
- [ ] Login / role redirects
- [ ] Seller application + credential email (~2 min with worker)
- [ ] Product listing with photos (Cloudinary)
- [ ] ImgBB URL import
- [ ] Guest checkout + order email
- [ ] Repair booking + map picker + ticket email
- [ ] Commission calculation & Pay Admin QR
- [ ] Admin payment verification
- [ ] Leaflet maps & tracking
- [ ] Website settings customization
- [ ] BAM Studio footer link present and not removable
- [ ] Unauthorized access returns 403

---

## License & Credit

© Mobile Clinic · Bishal Niraula  
Technology by [BAM Studio](https://bamstudio.argan.com.np/)
