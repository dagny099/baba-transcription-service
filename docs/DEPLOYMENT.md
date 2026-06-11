# TranscriptWorkbench — EC2 Deployment Guide

Covers deploying TranscriptWorkbench on a free-tier Amazon Linux 2023 EC2 instance (t2.micro),
with an optional custom domain and HTTPS via Nginx and Certbot.

---

## Prerequisites

- An AWS account with EC2 access
- A `.pem` key pair for SSH
- Your `OPENAI_API_KEY`
- (Optional) A registered domain name for HTTPS setup

---

## Step 1 — Launch the EC2 Instance

In the AWS Console:

1. Go to **EC2 → Launch Instance**
2. AMI: **Amazon Linux 2023** (free tier eligible)
3. Instance type: **t2.micro**
4. Key pair: create or select an existing `.pem` key
5. Security Group — add these inbound rules:

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Your IP | SSH |
| 8501 | TCP | 0.0.0.0/0 | Streamlit (direct access, before Nginx) |

6. Storage: increase to **20 GB gp2** (still free tier; the default 8 GB is tight with all deps)
7. Launch the instance

---

## Step 2 — Connect via SSH

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ec2-user@<YOUR_EC2_PUBLIC_IP>
```

---

## Step 3 — Add Swap Space

The Python dependencies (numpy, pyarrow, pandas, pillow) need more than 1 GB RAM during
installation. Add a 2 GB swapfile before installing anything:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
```

---

## Step 4 — Install System Dependencies

```bash
sudo dnf update -y
sudo dnf install -y git
```

Verify Python 3.12 is present — Amazon Linux 2023 ships with it:

```bash
ls /usr/bin/python*
# Expected: /usr/bin/python3  /usr/bin/python3.12  /usr/bin/python3.9  ...
```

**Install ffmpeg via static binary.** EPEL does not work on Amazon Linux 2023 (it requires RHEL);
the static build from johnvansickle.com is the reliable alternative:

```bash
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar -xf ffmpeg-release-amd64-static.tar.xz
sudo cp ffmpeg-*-amd64-static/ffmpeg /usr/local/bin/
sudo cp ffmpeg-*-amd64-static/ffprobe /usr/local/bin/
rm -rf ffmpeg-*-amd64-static* ffmpeg-release-amd64-static.tar.xz
ffmpeg -version && ffprobe -version
```

---

## Step 5 — Transfer or Clone the Code

**Option A — Git clone (recommended):**

```bash
git clone https://github.com/dagny099/baba-transcription-service.git
cd baba-transcription-service
```

**Option B — scp from your local machine:**

```bash
# Run this on your Mac, not on EC2
scp -i your-key.pem -r /Users/bhs/PROJECTS/baba-transcription-utility \
    ec2-user@<YOUR_EC2_PUBLIC_IP>:~/baba-transcription-service
```

> The local directory is `baba-transcription-utility`; the remote target keeps the GitHub
> repo name (`baba-transcription-service`) so all paths below match the `git clone` flow.

---

## Step 6 — Create the Virtual Environment

Use Python 3.12 (available on Amazon Linux 2023 without any extra installs):

```bash
cd ~/baba-transcription-service
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Installation takes a few minutes. The swap from Step 3 prevents out-of-memory failures.

---

## Step 7 — Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

Minimum required values for the OpenAI-only deployment:

```bash
OPENAI_API_KEY=sk-...
TRANSCRIPT_WORKBENCH_DATA_DIR=./data
MAX_UPLOAD_MB=50          # lower on t2.micro to reduce memory pressure; raise if you have headroom
DEFAULT_PROVIDER=openai
DEFAULT_MODEL=gpt-4o-mini-transcribe
```

> **Note:** `MAX_UPLOAD_MB` is enforced in the Streamlit UI (the uploader shows an error if
> the file exceeds it) and is also passed to Streamlit's `--server.maxUploadSize` via the
> systemd unit below. If you raise it, make sure the matching `client_max_body_size` in the
> Nginx config (Step 10d) is at least as large.

Leave AWS variables empty until the AWS Transcribe milestone is ready.

Save with `Ctrl+O`, exit with `Ctrl+X`.

---

## Step 8 — Test the App Directly

```bash
source .venv/bin/activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Open `http://<YOUR_EC2_PUBLIC_IP>:8501` in a browser. Confirm the app loads and the sidebar
shows the API key loaded from environment. Stop it with `Ctrl+C` before proceeding.

---

## Step 9 — Run as a Persistent systemd Service

Create the service file:

```bash
sudo nano /etc/systemd/system/transcript-workbench.service
```

Paste (adjust `ec2-user` if your username differs):

```ini
[Unit]
Description=TranscriptWorkbench Streamlit App
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/baba-transcription-service
EnvironmentFile=/home/ec2-user/baba-transcription-service/.env
ExecStart=/home/ec2-user/baba-transcription-service/.venv/bin/streamlit run app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.maxUploadSize ${MAX_UPLOAD_MB}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> **Note:** Once Nginx is in front (Step 10), change `--server.address 0.0.0.0` to
> `--server.address 127.0.0.1` and remove port 8501 from the Security Group.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable transcript-workbench
sudo systemctl start transcript-workbench
sudo systemctl status transcript-workbench
```

The app is now live at `http://<YOUR_EC2_PUBLIC_IP>:8501` and will restart automatically on reboot.

---

## Step 10 — Custom Domain with HTTPS (optional but recommended)

### 10a — Assign an Elastic IP

A free-tier instance gets a new public IP on every reboot. Assign an Elastic IP so the address
is stable:

1. EC2 → **Elastic IPs** → **Allocate Elastic IP address**
2. **Associate** it with your running instance

Point your domain's **A record** at the Elastic IP via your DNS provider. DNS propagation can
take a few minutes to several hours.

### 10b — Open ports 80 and 443

Add to your Security Group inbound rules:

| Port | Protocol | Source |
|------|----------|--------|
| 80 | TCP | 0.0.0.0/0 |
| 443 | TCP | 0.0.0.0/0 |

### 10c — Install Nginx and Certbot

```bash
sudo dnf install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx

sudo dnf install -y python3-certbot-nginx
```

### 10d — Configure Nginx as a Reverse Proxy

```bash
sudo nano /etc/nginx/conf.d/transcript-workbench.conf
```

Replace `your-domain.com` with your actual domain:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    # Allow large uploads. Must be >= MAX_UPLOAD_MB in .env.
    # Nginx's default is 1m, which causes 413 errors on any non-trivial audio file.
    client_max_body_size 200M;
    # Stream request bodies straight to Streamlit instead of buffering the full upload
    # to disk first — important on small EC2 instances and for snappier uploads.
    proxy_request_buffering off;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

> **If you raise or lower `client_max_body_size`, change `MAX_UPLOAD_MB` in `.env` to match**
> (and restart the systemd service so Streamlit picks up the new `--server.maxUploadSize`).
> If they drift apart, you'll get confusing errors — Nginx 413 at one ceiling, a Streamlit
> "file too large" toast at another.

Test and reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 10e — Get a Free SSL Certificate

```bash
sudo certbot --nginx -d your-domain.com
```

Certbot edits the Nginx config automatically and sets up renewal. Test renewal:

```bash
sudo certbot renew --dry-run
```

### 10f — Tighten the systemd Service

Now that Nginx is the public entry point, bind Streamlit to localhost only:

Edit `/etc/systemd/system/transcript-workbench.service` and change:

```
--server.address 0.0.0.0
```

to:

```
--server.address 127.0.0.1
```

Reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart transcript-workbench
```

Remove port **8501** from the Security Group inbound rules — it is no longer needed publicly.

Your app is now at `https://your-domain.com`.

---

## AWS Transcribe on EC2

When the AWS Transcribe milestone is ready, the EC2 instance should authenticate via an
**IAM role attached to the instance**, not stored access keys in `.env`.
See `docs/AWS_TRANSCRIBE_SETUP.md` — the EC2 credential section (Stage EC2-1 through EC2-5)
covers the full setup.

Short version:

1. Create an IAM role with `TranscriptWorkbenchTranscribePolicy` attached
2. Attach the role: EC2 → Actions → Security → Modify IAM role
3. Remove `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from `.env` on EC2

boto3 picks up the role credentials automatically via the instance metadata service.
Do not store long-lived AWS access keys on the server.

---

## Maintenance Reference

| Task | Command |
|------|---------|
| View live logs | `sudo journalctl -u transcript-workbench -f` |
| View last 50 log lines | `sudo journalctl -u transcript-workbench -n 50` |
| Restart app | `sudo systemctl restart transcript-workbench` |
| Pull latest code | `cd ~/baba-transcription-service && git pull` |
| Update and restart | `git pull && sudo systemctl restart transcript-workbench` |
| Check swap usage | `free -h` |
| Check disk usage | `df -h` |
| Nginx status | `sudo systemctl status nginx` |
| Reload Nginx config | `sudo systemctl reload nginx` |
