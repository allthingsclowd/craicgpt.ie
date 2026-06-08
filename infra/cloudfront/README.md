# CloudFront edge router — multi-lingual URLs

This directory enacts the `/en/`, `/de/`, … language routing for the static site
**via the AWS CLI**, not Terraform — see the caveat below.

## Files
- **`router.js`** — the CloudFront Function (viewer-request). It:
  1. **detects** language on a prefix-less request (cookie → `Accept-Language` → `en`) and
     **302**-redirects to `/<lang>/`, remembering the choice in a `cg_lang` cookie;
  2. **aliases** `/en/*` → `/*` (English content lives at the S3 root — no duplicate tree);
  3. rewrites `/<lang>/` (and any bare dir) → `…/index.html` (OAC→S3 needs this); and
  4. passes asset/content/media paths straight through (safe even if broadly attached).
- **`deploy-router.sh`** — idempotent: builds + publishes the function; with `--attach`,
  injects the viewer-request association on the distribution's **default** behavior
  (ETag-safe, shows a diff, prompts before the live write).

## Why AWS CLI and not `terraform apply`
`terraform/frontend` declares **no backend** → local state, and **that state is not in
this checkout** (the live stack was applied from another host). `terraform apply` from
here would see an empty state and try to **re-create** the live S3/CloudFront/ACM/Route53.
So the change is enacted imperatively here; the `.tf` carries the equivalent as
**NOT-APPLIED documentation** to reconcile/`import` later from wherever the state lives.

## Run it (admin creds — the put-only `craicgpt-publish` IAM can't modify CloudFront)
```bash
# creds pulled inline from 1Password (never printed); override field labels if needed.
cd infra/cloudfront
./deploy-router.sh                          # build + publish the function only (safe)
DIST_ID=<distribution-id> ./deploy-router.sh --attach   # also wire it onto the distribution
```

## Verify after deploy
```bash
curl -sI https://craicgpt.ie/            | grep -i location   # → /en/ (or detected lang)
curl -sI https://craicgpt.ie/de/         | grep -i HTTP       # → 200 (serves de/index.html)
curl -s  https://craicgpt.ie/de/content/<Y>/<M>/<D>/paper_content.json | head -c 60  # 200, no redirect
curl -sI -H 'Cookie: cg_lang=fr' https://craicgpt.ie/ | grep -i location  # → /fr/
```

## Cost
CloudFront Functions: **$0.10 / 1M invocations**, with a perpetual **2M/mo free tier**, and
attached only to page loads → effectively **€0** at this site's traffic.
