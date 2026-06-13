# Email Sharing Setup

The "Share via email" section in the Downloads & Share tab sends a transcript
email: the transcript is rendered into the email body, and the selected files
(markdown / text / JSON, optionally the audio) are attached.

Two transports are supported, selected by `EMAIL_PROVIDER` in `.env`. The
message, allowlist, size cap, and daily limit are identical for both — you can
switch transports at any time by changing one env var and restarting.

| | `smtp` (Gmail) | `ses` (AWS SES) |
|---|---|---|
| Setup time | ~5 minutes | Identity verification + IAM |
| Credentials | App password in `.env` | Ambient AWS creds (EC2 role) |
| From address | Your Gmail (or a Gmail "Send mail as" alias) | Any verified identity |
| Limits | ~500 emails/day, 25 MB | Sandbox: verified recipients only; 40 MB |

---

## How sending is kept safe (both transports)

The app is publicly reachable, so three layers prevent it from being used as
a spam relay:

1. **Recipient allowlist** — only addresses listed in `EMAIL_RECIPIENTS` can
   be selected, and the check is enforced server-side in
   `transcript_workbench/services/email.py`, not just in the UI.
2. **Daily limit** — the app refuses to send more than `EMAIL_DAILY_LIMIT`
   emails per UTC day (tracked in the `email_log` SQLite table).
3. **Attachment cap** — `EMAIL_MAX_ATTACHMENT_MB` (default 25) keeps messages
   under both Gmail's 25 MB limit and SES's 40 MB post-base64 limit.

---

## Option A — Gmail SMTP (quickest)

Requires a Google account with 2-Step Verification turned on (app passwords
don't exist without it).

1. Go to <https://myaccount.google.com/apppasswords>
2. Create an app password named e.g. `transcript-workbench`; Google shows a
   16-character password **once** — copy it
3. In `.env`:

```bash
EMAIL_PROVIDER=smtp
EMAIL_SENDER=you@gmail.com            # see note on From addresses below
EMAIL_RECIPIENTS=mom@example.com,you@gmail.com
SMTP_USERNAME=you@gmail.com           # the account that owns the app password
SMTP_PASSWORD=abcdefghijklmnop        # the 16-char app password, no spaces
```

4. Restart the service (`sudo systemctl restart transcript-workbench`)

> **From-address note:** Gmail rewrites the From header to the authenticated
> account unless the address is configured as an alias under Gmail →
> Settings → Accounts → **"Send mail as"**. If you already send as a custom
> domain address from Gmail (e.g. via an email forwarder), that alias works
> here too — set `EMAIL_SENDER` to it. Otherwise just use the Gmail address.

> **Security note:** the app password grants mail access to your Google
> account, so treat `.env` like a secret (it already holds your OpenAI key).
> You can revoke the app password instantly at the same URL if needed.

---

## Option B — AWS SES

Effectively free at personal volume; authenticates via the EC2 instance role
so no mail credentials live on disk. The trade-off is AWS setup ceremony.

### B1 — Verify the sender identity

1. AWS Console → **Amazon SES** — *the region matters*: identities are
   per-region, and the app uses `AWS_DEFAULT_REGION`. Pick one region and use
   it for both.
2. **Identities → Create identity** — either a single email address (click
   the confirmation link SES sends) or a whole domain (publish the DKIM
   CNAME records at your DNS host).

> **DNS gotcha:** when pasting TXT/CNAME values into your DNS host, paste
> *only* the value. A stray prefix like `Value: ` inside the record body
> makes it invalid — e.g. a DMARC record must begin exactly with `v=DMARC1`.
> Verify from a terminal with `dig TXT _dmarc.yourdomain.com +short`.

### B2 — Verify recipients (sandbox mode)

New SES accounts are sandboxed: every *recipient* must also be a verified
identity. Verify each address you plan to put in `EMAIL_RECIPIENTS` the same
way. (For a personal allowlist this is a feature — it enforces the allowlist
at the AWS level.) To send to unverified addresses, request production access
under **SES → Account dashboard**.

### B3 — Grant the EC2 role permission to send

Add to the instance role (same pattern as AWS Transcribe — no keys in `.env`):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ses:SendEmail", "ses:SendRawEmail"],
      "Resource": "*"
    }
  ]
}
```

For local development, the usual boto3 credential chain applies
(`AWS_PROFILE` etc.).

### B4 — Configure the app

```bash
EMAIL_PROVIDER=ses
EMAIL_SENDER=you@example.com          # the verified identity from B1
EMAIL_RECIPIENTS=mom@example.com,you@example.com
AWS_DEFAULT_REGION=us-west-1          # the region where you verified identities
```

Restart the service.

### B5 — Deliverability tips for custom domains

- If your domain's mail is *received* through a forwarding service
  (ImprovMX etc.), don't judge SES by emails you send to yourself — the
  forwarder-to-Gmail hop is the flakiest path there is, and Gmail often
  hides self-addressed forwarded mail. Test against a recipient that is a
  real, direct mailbox.
- Add `include:amazonses.com` to the domain's SPF TXT record.
- Publish a DMARC record: TXT at `_dmarc` with value
  `v=DMARC1; p=none; rua=mailto:you@yourdomain.com`.

---

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| `Username and Password not accepted` (SMTP) | Wrong app password, spaces included, or 2-Step Verification off |
| From address silently replaced (SMTP) | `EMAIL_SENDER` isn't a Gmail "Send mail as" alias — see Option A note |
| `Email address is not verified` (SES) | Recipient (sandbox) or sender identity not verified — B1/B2 |
| `AccessDenied` on `ses:SendRawEmail` | IAM policy missing from the instance role — B3 |
| `Could not connect to the endpoint URL` (SES) | Region mismatch — identities are per-region; check `AWS_DEFAULT_REGION` |
| "Daily email limit reached" | `EMAIL_DAILY_LIMIT` hit; raise it in `.env` and restart |
| Send history / audit | `email_log` table in `data/transcript_workbench.sqlite` |
