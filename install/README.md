# Hosting these files at spielos.xyz

Two files in this directory are designed to be served at specific paths
on `spielos.xyz`:

| File | URL | Purpose |
|---|---|---|
| `spielos` | `https://spielos.xyz/spielos` | The installer. Piped into `bash` by `curl -fsSL …/spielos \| bash`. Must be served with no extension and a `text/plain` (or any) content type — `bash` doesn't care. |
| `install.html` | `https://spielos.xyz/install` | The human-readable install page. The big copy box shows the curl command, explains what just happened, and points at the next step. |

`install.sh` stays in this directory as the canonical source. The
`spielos` file in this directory is a copy of it — kept under the URL
filename so the deploy step is a simple file copy.

## Deploy options

**Static host (Netlify / Cloudflare Pages / Vercel / S3+CloudFront / etc.)**
- Upload `spielos` to `/spielos` (no extension) at the domain root.
- Upload `install.html` to `/install.html` at the domain root (or
  rename to `install/index.html` if you prefer a directory URL).

**GitHub Pages (recommended — free, fast, custom domain)**
1. In the GitHub repo for this project, Settings → Pages → "Build and
   deployment" → Source: "Deploy from a branch", Branch: `main`, Folder:
   `/install`.
2. Settings → Pages → Custom domain: `spielos.xyz`. Add the CNAME
   record at your DNS provider (`spielos.xyz` → `<user>.github.io`).
3. In this folder, add a `CNAME` file containing just `spielos.xyz` on
   one line (GitHub will create it for you on first deploy).
4. The `spielos` file needs no extension; GitHub Pages will serve it
   as `application/octet-stream`, which `bash` reads fine.

**Other hosts**
- Anywhere that can serve a file with arbitrary path + content type.
- Apache/Nginx: just put the two files in the document root, no config
  needed.

## Curl command (for the docs + the install page)

```bash
curl -fsSL https://spielos.xyz/spielos | bash
```

This must match the URL where the `spielos` file is served.
