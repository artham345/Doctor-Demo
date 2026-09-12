# Everwell — Doctor website & appointment system

A single Django application with a public clinic website and a private doctor portal. PostgreSQL stores clinic configuration, working periods, patients, appointments, and a durable email outbox. The supplied branding and doctor identity are fictional demo content.

## Included

- Responsive home, doctor profile, database-driven services, contact form/inbox, privacy notice, and branded error pages.
- Guest booking with live availability, a 90-day booking window, breaks, leave, validation, and a private booking receipt/cancellation link.
- PostgreSQL transactions, per-doctor row locks, and a conditional unique constraint prevent double bookings. Overlapping appointment intervals are checked as well as start times.
- Doctor authentication, appointment search/filtering/pagination, status actions, patient histories, day/week/month calendar, schedule/leave management, services, and profile/photo editing.
- Transactional HTML/text email outbox with retries; local console backend; production SMTP worker.
- Secure defaults, CSRF, ownership checks, rate limits, no-store private responses, no analytics, and no patient accounts or medical-record features.
- Local Bootstrap 5 assets, accessible forms/focus states, metadata, Physician microdata, robots.txt, and sitemap.xml.
- Initial migrations, repeatable demo data, automated PostgreSQL tests, GitHub Actions, Gunicorn, WhiteNoise, S3 storage support, and a Render Blueprint.

## Project structure

```text
doctor_website/
├── manage.py
├── config/
│   ├── settings.py           # Environment-based development/production configuration
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── clinic/
│   ├── models.py             # Doctor, Service, Patient, Appointment, Schedule, Leave
│   ├── services.py           # Atomic booking and availability mutations
│   ├── forms.py
│   ├── views.py
│   ├── security.py
│   ├── middleware.py
│   ├── storage.py
│   ├── admin.py
│   ├── admin_forms.py
│   ├── migrations/0001_initial.py
│   └── management/commands/
│       ├── seed_demo.py
│       ├── remove_demo.py
│       ├── create_doctor.py
│       └── cleanup_operational_data.py
├── notifications/
│   ├── models.py
│   ├── services.py
│   ├── admin.py
│   ├── migrations/0001_initial.py
│   └── management/commands/send_notifications.py
├── templates/
│   ├── base.html
│   ├── public/
│   ├── appointments/
│   ├── doctor/
│   ├── includes/
│   ├── emails/
│   └── errors/
├── static/
│   ├── css/style.css
│   ├── js/{site,booking}.js
│   ├── images/favicon.svg
│   └── vendor/               # Bootstrap 5.3.8 and source maps
├── tests/test_clinic.py
├── .github/workflows/tests.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── compose.yaml
├── build.sh
├── gunicorn.conf.py
├── render.yaml
├── README.md
├── VERIFICATION.md
└── FILE_TREE.txt
```

The clinic domain is deliberately kept in one cohesive Django app. Notifications are a separate app and can later gain SMS/WhatsApp adapters. Doctor foreign keys and ownership-scoped queries support future expansion; version 1 allows one public doctor through a database constraint. [FILE_TREE.txt](FILE_TREE.txt) lists every delivered source file.

## Windows setup (VS Code)

Install Python 3.13 or 3.14, Git, and PostgreSQL 17. Open this `doctor_website` directory in VS Code. These commands are for the VS Code **Command Prompt** terminal unless labelled PowerShell.

```bat
python --version
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

PowerShell activation alternative:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
Copy-Item .env.example .env
```

If PowerShell blocks activation, use the Command Prompt terminal above, or run `venv\Scripts\python.exe` directly for each Python command. Do not weaken your machine-wide execution policy just to activate a virtual environment.

### PostgreSQL

Use the [official Windows installer](https://www.postgresql.org/download/windows/). Remember the `postgres` administrator password you choose. In SQL Shell (psql), connect as `postgres`, then run:

```sql
CREATE ROLE clinic WITH LOGIN CREATEDB;
\password clinic
CREATE DATABASE clinic OWNER clinic;
```

The password prompt keeps the password out of SQL command history. `CREATEDB` is needed only on the development role to run Django tests. Production must use the restricted Render database role.

Edit `.env` and set your actual password:

```dotenv
DEBUG=True
DATABASE_URL=postgresql://clinic:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5432/clinic
SECRET_KEY=YOUR_RANDOM_SECRET
ALLOWED_HOSTS=localhost,127.0.0.1
SITE_URL=http://127.0.0.1:8000
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
TIME_ZONE=Asia/Kolkata
```

Generate a secret, then paste it into `.env`:

```bat
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

URL-encode reserved password characters such as `@`, `:`, `/`, and `#` in `DATABASE_URL`. There is no SQLite fallback; development and production both use PostgreSQL.

If you already have Docker Desktop, `compose.yaml` provides an alternative database. In PowerShell:

```powershell
$env:POSTGRES_PASSWORD = Read-Host 'Choose a development database password'
docker compose up -d db
```

Use the same password in `DATABASE_URL`. The database port binds only to localhost. Do not use `docker compose down -v` unless you intend to delete the database volume.

### Migrate, seed, and run

```bat
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Open [the public website](http://127.0.0.1:8000/) or [the doctor login](http://127.0.0.1:8000/doctor/login/).

**Local demo credentials only:**

```text
Username: demo.doctor
Password: DemoClinic!2026
```

`DEMO_PASSWORD` can override the initial demo password. Re-running the seed command preserves existing data and passwords. The command refuses to seed when `DEBUG=False`, when a real public clinic exists, or when the demo username belongs to a non-demo user. The seeded doctor is not a staff user or superuser.

In a second activated terminal, start email delivery:

```bat
python manage.py send_notifications --watch
```

The local console backend prints email messages to that terminal; it does **not** deliver to an inbox. Use only demo data with console email. The outbox is populated within the booking transaction, so no email is queued if booking rolls back. The worker retries failed delivery with backoff and removes message bodies after successful delivery. Delivery is at least once: a process crash after SMTP accepts a message can cause a duplicate on retry.

To create the real clinic, remove demo data first, then create a separate real doctor account:

```bat
python manage.py remove_demo --confirm
python manage.py create_doctor
```

Removal deletes **all** records belonging to a marked demo clinic, including any test bookings added through its website. Never collect real patient data in a demo clinic. The real doctor setup prompts for a strong password without putting it in shell history. Complete the profile, services, and schedule through the portal before opening bookings to patients.

## Testing

Use a development database role with permission to create a test database. Never point the test command at production.

```bat
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tests --verbosity 2
```

The suite covers dynamic slots, breaks, past/closed/leave dates, validation, public booking, double booking, a direct database duplicate, simultaneous booking requests, login, portal authorization, doctor ownership, cancellation tokens, status changes, existing-booking protection during schedule/leave changes, patient identity preservation, email delivery/retry, public pages, contact messages, CSRF, and rate limits.

`python manage.py test tests --keepdb` preserves the isolated test database between runs. `TEST_DATABASE_NAME` optionally selects a dedicated test database name. GitHub Actions also runs migrations and production checks against PostgreSQL 17.

For production configuration validation, set the production environment variables in a separate terminal and run:

```bat
python manage.py check --deploy --fail-level WARNING
python manage.py collectstatic --noinput
```

See `VERIFICATION.md` for the checks actually performed during delivery and any environment limitations. Do not infer live SMTP, S3, DNS, or Render verification from local tests.

## How booking works

1. `/availability/?date=YYYY-MM-DD` returns only available times and durations, never patient details.
2. The form validates patient inputs on the server. Dates are checked against the clinic timezone, current time, 90-day window, schedule, and leave.
3. Inside `transaction.atomic()`, booking locks the doctor's row with `select_for_update()`, recalculates availability, then creates the patient/appointment and email outbox rows.
4. A conditional PostgreSQL unique constraint also prevents two non-cancelled appointments at the same doctor/date/start time. Interval checks protect against overlaps after duration changes.
5. A private, random 256-bit cancellation token is returned once. Only its SHA-256 digest is stored on the appointment. A cancellation link may exist temporarily in the email outbox until delivered. Receipt pages do not display patient names, phones, messages, or reasons.
6. The clinic confirms the request. Confirmation and cancellation enqueue patient emails when an email was supplied.

The reference is human-readable, for example `APT-2026-7DA9184AB3`, with a random suffix rather than a guessable sequence. All non-cancelled statuses retain their occupied slot; cancellation releases it. Cancelled appointments cannot be reactivated. Confirmed appointments can be completed or marked no show only after their start time. Patient cancellation is permitted before the start time; after that, the patient must call the clinic.

Schedule and leave mutations lock the same doctor row as booking. Schedule edits cannot invalidate upcoming appointments. Doctors must cancel affected appointments before changing those working periods or adding leave. Different demographic submissions sharing a phone number never overwrite an existing patient's identity. Exact matches reuse a patient record; changed details may produce a separate record rather than guessing identity.

## Doctor user guide

1. Open `/doctor/login/` and sign in with the account provided by your administrator.
2. **Dashboard:** See today's appointments, pending requests, and new contact messages.
3. **Appointments:** Search for a patient/reference, filter by date/status, and choose **View**. Confirm a pending request. After the visit, mark it completed or no show. Cancel when necessary; a confirmation dialog prevents accidental cancellation.
4. **Calendar:** Switch between Day, Week, and Month. Use the arrows to move through dates. Click an appointment to open its details. Mobile month/week layouts become a readable agenda.
5. **Patients:** Search names or phone numbers and view contact information and appointment history. This is not a medical-record system.
6. **Schedule:** Add each working period separately. For a lunch break, create `10:00–13:00` and `17:00–20:00`. Set the appointment duration in minutes. Edit, disable, or delete periods as needed; resolve affected bookings first.
7. **Leave / Holidays:** Add unavailable dates. Remove leave to reopen that date, subject to your normal weekly schedule.
8. **Services:** Add or edit the services shown publicly. Turn off **Is active** to hide a service.
9. **Profile:** Update your name, photo, qualifications, contact details, clinic details, and social links. Select **Change password** to update your password.
10. **Messages:** Read contact-form enquiries and mark them read. Reply by calling the patient or using your clinic's email account.
11. Always sign out on shared devices. Keep your password and patient information private.

If you forget the password, contact the website administrator. The administrator can reset it with `python manage.py changepassword DOCTOR_USERNAME`. No insecure default reset link or password is supplied.

## Django administration

`/admin/` uses the separate superuser created above. Manage doctor profiles, services, patient contact details, appointment statuses, working schedules, leaves, and contact messages there. The admin appointment and schedule forms use the same transaction-aware services and doctor row locks as the portal. Existing bookings remain protected, invalid status transitions are rejected, and status changes enqueue notifications. Create new appointments through the booking flow; delete working periods through the doctor portal. Appointment and patient deletion is deliberately unavailable through routine admin screens. Email delivery metadata is read-only. Do not grant superuser access to the doctor for routine daily work.

## GitHub

Create an empty private GitHub repository, then run in this project directory. Replace `YOUR_USERNAME` and repository name with yours:

```bat
git init
git add .
git status
git commit -m "Build clinic website and secure appointment system"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/doctor-website.git
git push -u origin main
```

Before committing, confirm `.env`, uploaded photos, database dumps, patient data, and virtual environments are excluded. The provided `.gitignore` excludes local secrets, media, generated static files, and caches. Commit migrations and the vendored Bootstrap files. The project has no repository-specific credentials.

## Render deployment

The Blueprint creates **one web application**, one private PostgreSQL database, and a background email worker. The worker is not a second website. The supplied plans (`0.5c-512mb` web/worker and `0.1c-256mb` PostgreSQL) are paid; review Render's displayed costs before applying the Blueprint. No Render resources are provisioned by this project automatically.

1. Push this project root to GitHub.
2. In Render, create a **Blueprint** from the repository containing `render.yaml`.
3. Enter the prompted secrets and site values for `clinic-web`. Common non-secret settings and the generated application secret live in `clinic-shared`; the worker references the web service’s SMTP and site values. Render ignores `sync: false` inside environment groups, so all prompts are deliberately defined on the web service. For initial deployment, use the assigned `https://YOUR-SERVICE.onrender.com` address for `SITE_URL` and `CSRF_TRUSTED_ORIGINS`, and its hostname for `ALLOWED_HOSTS`.
4. Set SMTP host, port, username, password, and a verified `DEFAULT_FROM_EMAIL`. The SMTP username does not have to equal the doctor's contact email.
5. Apply the Blueprint. Check the web and worker logs for successful startup.
6. In the web service's Shell, run `python manage.py createsuperuser`, then `python manage.py create_doctor`.
7. Sign into the doctor portal, complete real profile details, services, and working periods, then test a booking and both emails with addresses you control.

Exact web service settings:

| Setting | Value |
|---|---|
| Runtime | Python 3.13 |
| Build command | `bash build.sh` |
| Pre-deploy command | `python manage.py migrate --noinput` |
| Start command | `gunicorn config.wsgi:application --config gunicorn.conf.py` |
| Health check | `/health/` |
| Database | `DATABASE_URL` from the Render database connection string |
| Email worker start | `python manage.py send_notifications --watch` |

Render's pre-deploy migrations are separate from the build; the Blueprint uses a paid service plan that supports this. `build.sh` installs dependencies and collects static assets. WhiteNoise serves the fingerprinted/compressed files. Gunicorn access logs are disabled so private token paths and search details are not logged by the application. Review proxy/provider log retention separately.

Production requires `DEBUG=False`, a unique long `SECRET_KEY`, explicit hosts, a canonical HTTPS `SITE_URL`, matching CSRF origins, and PostgreSQL. `TRUST_PROXY=True` is intended only behind Render's trusted TLS-terminating proxy. Secure session/CSRF cookies, HTTPS redirects, HSTS, and a restrictive content security policy are enabled in production. Test HTTPS before enabling traffic; HSTS covers subdomains, so all clinic subdomains must support HTTPS.

The application rate limit uses the direct peer address, not caller-supplied forwarded headers. Behind a shared reverse proxy this can conservatively group clients together. Configure an edge rate limit using the provider's verified client IP if traffic warrants it; do not blindly trust `X-Forwarded-For`.

### Durable photo storage

Local development uses `media/`. Production deliberately rejects new uploads until durable storage is configured; it never silently stores patient-facing media on Render's temporary filesystem.

Create a private S3 bucket (or S3-compatible service), grant the application narrowly scoped object read/write permissions, and add these values to the shared environment group:

```dotenv
USE_S3=True
AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY
AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY
AWS_STORAGE_BUCKET_NAME=YOUR_BUCKET
AWS_S3_REGION_NAME=ap-south-1
```

Set `AWS_S3_ENDPOINT_URL` only for a compatible alternative provider. Signed URLs display private-bucket photos. The application generates random upload filenames and accepts only validated JPEG, PNG, or WebP images up to 5 MB and 6000 pixels per dimension. Existing local media is not automatically migrated; upload the doctor's photo again after enabling S3. The `STORAGES` configuration is the replacement point for another storage backend.

## Custom domain

1. In the Render web service, open **Settings → Custom Domains** and add `doctorwebsite.com` and, if desired, `www.doctorwebsite.com`.
2. At your DNS provider, enter the exact records Render displays for the apex and `www` host. Use the provided targets rather than copying an IP address from an unrelated tutorial.
3. Wait for DNS verification and Render's TLS certificate to become active.
4. Set the canonical origin and host list, then sync the Blueprint so worker references refresh, and redeploy both services:

```dotenv
SITE_URL=https://doctorwebsite.com
ALLOWED_HOSTS=doctorwebsite.com,www.doctorwebsite.com,YOUR-SERVICE.onrender.com
CSRF_TRUSTED_ORIGINS=https://doctorwebsite.com,https://www.doctorwebsite.com,https://YOUR-SERVICE.onrender.com
```

5. Test public pages, login, booking, email links, cancellation, and calendar download on the custom domain. `SITE_URL` determines links in outgoing emails and robots.txt. Choose one canonical hostname and configure the redirect in your hosting/domain setup if using both apex and `www`.

## Production handoff checklist

- Replace every demo identity, biography, qualification, address, phone number, and testimonial. The sample review displays only when the doctor is marked as demo. Obtain the doctor's approval for all public content.
- Remove demo data; create unique real doctor and administrator credentials. Store recovery details with the client securely.
- Configure SMTP, verify sender/domain authentication with the mail provider, start the worker, and test booking/confirmation/cancellation email delivery. Monitor retry counts.
- Configure durable photo storage and verify upload/display after a redeploy.
- Check HTTPS, secure cookies, exact allowed hosts/origins, `DEBUG=False`, and environment secrets. Run deployment checks.
- Enable PostgreSQL backups and recovery appropriate to the clinic's needs. Perform a restore test. Restrict external database access and use TLS for remote database connections.
- Agree on patient-data retention, deletion procedures, hosting region, authorized users, and a clinic-approved privacy notice. This code does not claim a jurisdiction-specific compliance certification.
- Limit access to the repository, Render, database, email provider, bucket, and admin. Review access when staff leave. Apply dependency/security updates through the test pipeline.
- Test the actual domain on mobile and desktop. Verify the clinic timezone and real schedule, leave behavior, booking, and cancellation.
- Deliver the domain/hosting ownership, renewal dates, backup instructions, and this Doctor User Guide to the doctor.

For routine cleanup, run `python manage.py cleanup_operational_data` periodically. This removes expired rate-limit counters and old delivered email metadata, not patient appointments. Use Django's `clearsessions` command periodically as well. Decide patient retention with the clinic before implementing any patient-data deletion policy.

## Operational boundaries

There are no prescriptions, diagnoses, insurance, payments, patient accounts, or AI features. This is an appointment system. Appointment emails omit reasons/messages and keep detailed information in the authorized portal. Contact-form responses are handled by the clinic. A patient's optional email is not identity verification; the cancellation link is a bearer credential.

The application is prepared for GitHub and Render, but no repository push, paid infrastructure, real domain change, external email delivery, or S3 upload is claimed without those accounts and configuration being supplied. PostgreSQL, application behavior, and deployment configuration can be verified locally; actual provider integrations must be checked in the client's environment.

## Reference documentation

- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Django database transactions](https://docs.djangoproject.com/en/5.2/topics/db/transactions/)
- [Render Django deployment](https://render.com/docs/deploy-django)
- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Render custom domains](https://render.com/docs/custom-domains)
- [django-storages S3 configuration](https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html)

Bootstrap 5.3.8 is vendored under its [MIT license](https://github.com/twbs/bootstrap/blob/v5.3.8/LICENSE); the complete notice is included in `static/vendor/LICENSE.bootstrap`, and the license banner remains in each asset. No external image or font service is required to render the site.
