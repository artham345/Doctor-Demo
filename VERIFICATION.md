# Delivery verification

Verified on 12 September 2026 using Python 3.14, Django 5.2.17, and an actual PostgreSQL 17.11 database on Windows. Test data was fictional. The application and its initial migrations were exercised against PostgreSQL, with no SQLite substitution.

## Automated results

```text
Ran 34 tests in 19.953s
OK
```

The critical concurrency test opens separate database connections in two threads and attempts the same appointment simultaneously. Exactly one booking succeeds. A separate test verifies that a direct duplicate insert fails at the PostgreSQL constraint.

| Check | Result and evidence |
|---|---|
| Django starts | Passed; development server served public and authenticated pages in a browser. |
| Initial migrations | Passed on a newly initialized PostgreSQL database. |
| Model/migration consistency | `makemigrations --check --dry-run` reported no changes. |
| Public pages | Home, about, services, contact, booking, privacy, login, robots, sitemap, and health endpoint returned successfully. |
| Guest booking | Passed automated form/integration tests and a real browser submission. |
| Dynamic availability | Tests cover working periods, variable durations, breaks, closed days, leave, past dates/times, and occupied intervals. |
| Double booking | Passed transaction/concurrency test and database uniqueness test. |
| Patient cancellation | Valid token works; invalid token is rejected; cancelled slot reopens. Browser confirmation dialog and cancellation succeeded. |
| Login and authorization | Doctor login/logout passed; unauthenticated access redirects; cross-doctor records are inaccessible. |
| Appointment statuses | Valid transitions work; invalid/reactivation/premature completion transitions are rejected. |
| Schedule and leave | Add/edit/delete flows tested; changes that invalidate existing appointments are rejected. |
| Patients | Search/history available; differing demographic submissions do not overwrite an existing patient. Search terms stay out of URLs. |
| Email architecture | HTML/text messages, outbox creation, successful delivery, and retry behavior tested with Django's in-memory backend and simulated delivery failures. |
| Django admin | Appointment changes and schedule validation tested through admin forms and requests; protected mutations use shared booking services. |
| CSRF and request handling | Missing CSRF token is rejected; browser same-origin form submissions work; contact/booking/login throttles tested. |
| Production security settings | `check --deploy --fail-level WARNING` passed with no issues. |
| Production static files | `collectstatic --noinput` passed; fingerprinted CSS, JavaScript, and favicon returned successfully through WhiteNoise. |
| Production smoke checks | With `DEBUG=False`, HTTPS requests served all public and portal pages; HTTP redirected; HSTS, nosniff, and private no-store headers verified. |
| Error handling | Branded error pages included; the 500 response rendered with the clinic database context deliberately unavailable. |
| Source/package audit | Python syntax checked; YAML parsed and local configuration references checked; archive integrity checked. |
| Documentation | Windows/PostgreSQL/env setup, demo/admin setup, testing, GitHub, Render, custom domain, storage, production checklist, and doctor guide included in README. |

## Browser and responsive review

The in-app Chromium browser was used at **375, 768, 1024, and 1440 pixels**. All 64 combinations below had no page-level horizontal overflow. Tables can scroll within their own containers when needed.

- Seven public screens at four widths: home, about, services, contact, booking, privacy, and doctor login — 28 checks.
- Nine doctor screens at four widths: dashboard, appointments, patients, schedule, leave, services, profile, messages, and calendar — 36 checks.

Home, booking, portal, and calendar screens were visually inspected. The mobile navigation/offcanvas, calendar Day/Week/Month views, guest booking, private receipt, cancellation confirmation, doctor login, and logout were exercised. The browser check produced no warning/error console entries. These checks do not represent a full assistive-technology audit or testing on every physical device/browser.

Two browser issues discovered during verification were fixed: a referrer policy that interfered with CSRF on form submissions, and mobile table overflow caused by visually hidden accessibility text. The updated flows and layouts were checked again successfully.

## Environment-specific notes

- The local automation sandbox prevented PostgreSQL from signalling a checkpoint while dropping a test database. The successful final suite used `--keepdb` against a dedicated disposable test database. Ordinary Windows installations and GitHub Actions can use the standard command in README; keeping the isolated test database is optional.
- The sandbox also restricted normal virtual-environment package installation. Verification used local compatible wheels fetched from PyPI with their published SHA-256 hashes verified. No custom runtime, database cluster, installed packages, or sandbox workaround is included in the application archive. The project uses the normal `requirements.txt` installation instructions.
- Linux Gunicorn startup and Render's hosted deployment were not run on this Windows machine. Production Django configuration, WSGI application behavior, and static serving were checked locally. The GitHub Actions workflow is supplied but has not run on GitHub.

## External integrations awaiting client configuration

The Render Blueprint was reviewed against the official Blueprint documentation and locally checked for valid YAML and consistent environment/service/database references. **No Render resources were provisioned, and Render has not executed or validated this deployment.**

Real SMTP delivery, S3 credentials/uploads, GitHub push, Render startup, DNS, custom-domain TLS, database backups/restores, and provider log retention require the client's accounts and configuration. They are not claimed as verified. Follow the README deployment and handoff checks before accepting real appointments.

All shipped names, qualifications, addresses, reviews, and demo credentials are sample content. The doctor photograph and map are explicit placeholders as requested. Replace them with clinic-approved content before launch; keep the demo account out of production.
