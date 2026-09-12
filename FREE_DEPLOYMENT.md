# Free deployment: Render + Neon + Gmail + optional Cloudinary

This is the current deployment guide. `render.yaml` creates one **Free** Render web service. It does not create a paid database or background worker. `render.paid.yaml` is the previous paid architecture and is not needed here. No custom domain is required.

## What runs

The website saves the booking and email outbox in PostgreSQL first. After the transaction commits, it immediately tries each new email through Gmail's HTTPS API. An email failure never undoes a saved booking. Confirmation and cancellation follow the same flow.

An optional GitHub Actions job runs hourly at minute 23 and POSTs to a token-protected retry endpoint. Each call handles at most two due emails; it cannot create arbitrary messages or return patient information. Successful sends clear the stored message bodies. Failed messages remain queued with backoff. A large backlog can take multiple hours to clear. The command `send_notifications` remains available for manual recovery, but no continuous second terminal is required once the website and scheduler are configured.

Delivery is at least once: a timeout or crash after Gmail accepts a message can result in a duplicate retry. A successful API response means Gmail accepted the message, not that the recipient's inbox placement is guaranteed.

## 1. Google account authorization (on your Windows laptop)

Use a Gmail account the clinic controls. Patients do not sign in to Google, and you do not need a Google Workspace subscription or your own domain. Do not enter the Gmail account password in this application.

1. Open https://console.cloud.google.com/ and create a project for the clinic sender.
2. Under **APIs & Services → Library**, enable **Gmail API**. This setup does not require purchasing Google Cloud services.
3. Configure **Google Auth Platform** (the OAuth consent screen): enter an app name, contact email, and choose **External** for a normal Gmail account.
4. In **Data Access**, add only `https://www.googleapis.com/auth/gmail.send`. The application needs permission to send mail, not read the inbox.
5. While Testing, add the sender Gmail account as a test user under **Audience**.
6. Under **Clients**, create an OAuth client of type **Desktop app**. Copy its client ID and client secret. The authorization helper uses a temporary localhost callback; no custom domain or hosted callback URL is needed.
7. In your local project `.env`, add:

```dotenv
GMAIL_CLIENT_ID=YOUR_DESKTOP_CLIENT_ID
GMAIL_CLIENT_SECRET=YOUR_DESKTOP_CLIENT_SECRET
GMAIL_SENDER=YOUR_CLINIC_ACCOUNT@gmail.com
```

8. From the project folder, with your virtual environment activated:

```powershell
pip install -r requirements.txt
python manage.py authorize_gmail
```

9. The browser opens Google's consent page. Sign in with that same clinic sender account and authorize the send permission. Only authorize the project you created. The helper does not send an email.
10. The command saves `GMAIL_REFRESH_TOKEN=...` in `.env.gmail`, which is excluded from Git. Copy that line into your local `.env` and later into Render's environment settings. Keep the file private. It is not automatically loaded.

**Testing expires:** Google Testing-mode authorizations for this scope expire after seven days. For ongoing use, review Google's personal-use exception, set the OAuth app's publishing status to **In Production**, and authorize again. Google may still show an unverified-app warning and apply user caps; this application authorizes only the clinic's sender account. Publishing is not the same as Google verification. Follow Google's requirements if you expand access. If Google or your organization blocks consent, resolve that before relying on delivery. To authorize again, first move the old `.env.gmail` to a secure location outside the repository.

## 2. Enable local Gmail delivery

Replace the existing EMAIL_BACKEND and DEFAULT_FROM_EMAIL lines in `.env` (do not leave conflicting duplicates):

```dotenv
EMAIL_BACKEND=notifications.gmail_backend.EmailBackend
EMAIL_SEND_IMMEDIATELY=True
DEFAULT_FROM_EMAIL=Clinic <YOUR_CLINIC_ACCOUNT@gmail.com>
```

Keep the three OAuth values and `GMAIL_SENDER` from step 1. `DEFAULT_FROM_EMAIL` must use that exact sender account. SMTP/Resend settings are no longer used by this backend. Restart Django, make a test booking using an address you control, then verify receipt in Gmail Sent and the recipient inbox. Verify the doctor's profile email too. Existing queued messages are retained; review their recipients before manually retrying old demo messages.

To check counts and failure categories without showing recipients or message bodies:

```powershell
python manage.py shell -c "from notifications.models import EmailNotification; from django.db.models import Count; print(list(EmailNotification.objects.filter(sent_at__isnull=True).values('last_error').annotate(count=Count('id'))))"
```

Failure categories: GmailConfigurationError means missing values or a mismatched From address; GmailAuthorizationError means authorization needs renewal; GmailPermissionError means Gmail rejected access (check API enablement, scopes and account limits); GmailQuotaError means Gmail returned a quota response. GmailDeliveryError covers other delivery/network failures. No provider body or secret is logged. A local manual retry uses `python manage.py send_notifications`; backoff still applies.

## 3. Neon Free PostgreSQL

Create a **Free** project at https://neon.com/. Copy the connection string from **Connect**, keeping its SSL parameters. Set it as `DATABASE_URL` locally and on Render. Do not commit it.

The settings require PostgreSQL. Do not use SQLite on Render: its local disk is temporary. If switching from SQLite, this does not migrate existing patients or bookings automatically. Keep the original database as a backup.

Initialize a fresh Neon database from the laptop (Render Free has no interactive Shell):

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py create_doctor
```

Use different usernames for the administrator and doctor. If these accounts already exist in Neon, skip creating them again. Do not seed a real clinic with demo data. Do not run tests against the deployment database.

## 4. GitHub and Render Free

Push the source to a private GitHub repository with `manage.py` and `render.yaml` at its root. `.env`, `.env.gmail`, media, and local databases must remain excluded.

In Render, choose **New → Blueprint**, select that repository and `render.yaml`, and verify it proposes exactly one web service on the **Free** plan. If you already deployed paid resources, this new file does not delete or stop those resources; inspect billing and preserve data before retiring them yourself.

The Blueprint configures:

| Setting | Value |
|---|---|
| Build | `bash build.sh` |
| Start | `python manage.py migrate --noinput && gunicorn config.wsgi:application --config gunicorn.conf.py` |
| Health check | `/health/` |
| Email backend | `notifications.gmail_backend.EmailBackend` |
| Immediate delivery | `True` |
| Database | Your external Neon connection string |

Enter these prompted values:

```dotenv
DATABASE_URL=YOUR_NEON_CONNECTION_STRING
GMAIL_CLIENT_ID=YOUR_DESKTOP_CLIENT_ID
GMAIL_CLIENT_SECRET=YOUR_DESKTOP_CLIENT_SECRET
GMAIL_REFRESH_TOKEN=YOUR_REFRESH_TOKEN
GMAIL_SENDER=YOUR_CLINIC_ACCOUNT@gmail.com
DEFAULT_FROM_EMAIL=Clinic <YOUR_CLINIC_ACCOUNT@gmail.com>
SITE_URL=https://YOUR_ACTUAL_SERVICE.onrender.com
ALLOWED_HOSTS=YOUR_ACTUAL_SERVICE.onrender.com
CSRF_TRUSTED_ORIGINS=https://YOUR_ACTUAL_SERVICE.onrender.com
```

If the actual Render hostname isn't assigned at the prompt yet, use `https://localhost` for the two origin values and `localhost` for ALLOWED_HOSTS temporarily. The app automatically permits Render's assigned hostname. Once provisioned, replace all three values with the real address and redeploy **before booking or sending any email**, so links are correct.

Render generates SECRET_KEY and EMAIL_RETRY_TOKEN. Keep both stable across redeploys. DEBUG is False and HTTPS security is enabled. Cloudinary starts disabled so unresolved image credentials do not prevent launch.

If creating a Web Service manually instead, select **Free**, use the commands above, and enter the same environment variables plus `DEBUG=False`, `TRUST_PROXY=True`, `TIME_ZONE=Asia/Kolkata`, `USE_S3=False`, `USE_CLOUDINARY=False`, `EMAIL_SEND_IMMEDIATELY=True`, and the Gmail backend. Generate independent random SECRET_KEY and EMAIL_RETRY_TOKEN values.

## 5. Enable hourly retries in GitHub

The workflow `.github/workflows/retry-emails.yml` is disabled until you opt in with a repository variable. It only makes one HTTPS request; it does not receive Gmail credentials or database access.

1. Go to **Repository Settings → Secrets and variables → Actions**.
2. Add repository secrets:
   - `EMAIL_RETRY_URL`: `https://YOUR_ACTUAL_SERVICE.onrender.com/internal/retry-emails/` (include the trailing slash).
   - `EMAIL_RETRY_TOKEN`: copy the generated value from Render. It must match exactly and be at least 32 characters long.
3. Add a repository **variable** `ENABLE_EMAIL_RETRIES` with value `true`.
4. Ensure the workflow is on the default branch. In **Actions → Retry clinic emails**, use **Run workflow** once to check it.
5. Keep workflow failure notifications enabled. Failures can indicate expired Gmail authorization, quota exhaustion, wrong retry credentials, or hosting downtime.

The schedule is hourly at minute 23 UTC. GitHub may delay or drop scheduled jobs; it is not a guaranteed deadline. Public repository schedules can be disabled after 60 days without activity. The endpoint processes at most two due messages per call and cannot be used to submit arbitrary emails. Unauthenticated requests return 403. Do not put the token in a URL or browser link.

## 6. Photo uploads (optional)

Cloudinary Free can store public doctor photos. Resolve the API key's create/upload permission first. In `render.yaml`, change USE_CLOUDINARY to `True`, push, and add CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in Render. Leave USE_S3=False. Upload the photo again in Doctor → Profile; old local images do not transfer automatically. Existing image validation and the Cloudinary configuration are retained.

## 7. Staying within a zero budget

- Render: choose the Free service, no paid worker or Render database. Free sites sleep after 15 minutes idle and can take about a minute to wake. Quotas and suspension rules apply.
- Neon: remain on Free and monitor compute, storage, and transfer usage.
- Cloudinary: remain on the Free Image and Video API plan and within its credit allowance.
- GitHub: Free private repositories have 2,000 included standard-runner minutes per month, shared across the account. An hourly retry job capped at two minutes plans for up to 1,488 minutes in a 31-day month, leaving about 512 for tests and other workflows. Manual retries also consume minutes. This estimate is not a billing guarantee. Keep paid usage blocked (no payment method, or an Actions budget with stop-usage enabled); check all other account usage. The workflow itself uploads no artifacts and uses no cache storage.
- Gmail: API quotas and account sending limits apply. This is for low-volume appointment notices, not bulk mail. Gmail acceptance does not guarantee inbox delivery.

Free tiers may change, pause, or run out. No service was purchased or provisioned by these code changes. This is suitable for low-volume testing/piloting with explicit awareness of interruptions, not an uptime guarantee for a clinic.

## Final verification before handoff

Verify the deployed site, login, real working periods, booking, both recipient emails, confirmation and cancellation emails, private email links, calendar download, and Cloudinary photo if enabled. Run the retry workflow manually. Check backups and recovery for your database. Record who owns the Gmail account and how to renew its OAuth authorization.

## Sources

- Gmail send API: https://developers.google.com/workspace/gmail/api/guides/sending
- Google OAuth token lifecycle: https://developers.google.com/identity/protocols/oauth2
- Testing consent expiration: https://support.google.com/cloud/answer/15549945
- Personal-use verification exception: https://support.google.com/cloud/answer/13464323
- Render Free limits: https://render.com/docs/free
- Neon Free: https://neon.com/pricing
- GitHub included usage: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- GitHub schedules: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Cloudinary Free: https://cloudinary.com/pricing
