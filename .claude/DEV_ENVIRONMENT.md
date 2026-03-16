# Developer Environment — Balazs Bekei (bekeib)

## Machine

- **Hardware**: AMD Ryzen 7 PRO 5850U with Radeon Graphics, 32GB RAM, 1TB SSD
- **OS**: Windows 11 Pro
- **Username (Windows)**: bekei / BALAZS_DESKTOP\bekei
- **Username (Linux)**: bekeib

---

## Disk Layout

| Drive | Purpose |
|-------|---------|
| `C:` | Windows system, installed apps, nothing dev-related |
| `D:` | All dev work — WSL2 virtual disk, projects, backups |

```
D:\
  WSL\
    Ubuntu\          ← WSL2 virtual disk (moved here from C:)
    backups\         ← periodic wsl --export snapshots
  projects\          ← source code (symlinked into WSL2 as ~/projects)
```

---

## WSL2

- **Distro**: Ubuntu 24.04 LTS
- **Version**: WSL2
- **Virtual disk location**: `D:\WSL\Ubuntu\`
- **Home directory**: `/home/bekeib`
- **Projects directory**: `/home/bekeib/projects` → symlinked to `/mnt/d/projects`
- **Default shell**: zsh + Oh My Zsh
- **zsh plugins**: git, zsh-autosuggestions, zsh-syntax-highlighting
- **Auto cd**: `cd ~/projects` on terminal open (set in `~/.zshrc`)

### Backup strategy
```powershell
# Periodic snapshot (run from PowerShell before any major change)
wsl --export Ubuntu D:\WSL\backups\ubuntu-YYYY-MM-DD.tar
```

---

## Terminal

- **App**: Windows Terminal
- **Default profile**: Ubuntu (WSL2)
- **Starting directory**: `/home/bekeib/projects`

---

## Shell (PowerShell)

- **Version in use**: PowerShell 7 (Core)
- **Note**: PowerShell 5.1 (Windows built-in) has initialization issues on this machine — always use PS7

---

## Docker

- **App**: Docker Desktop (latest)
- **Backend**: WSL2 engine
- **WSL Integration**: enabled for Ubuntu
- **Usage**: Dev Containers via VS Code

---

## Editor

- **Primary**: VS Code (Windows install, connects to WSL2 via Remote WSL extension)
- **VS Code extensions (global)**:
  - WSL (Microsoft)
  - Dev Containers (Microsoft)
  - GitLens (Microsoft)

### How to open a project
Always open from inside the Ubuntu terminal:
```bash
cd ~/projects/PROJECT_NAME
code .
```
The green badge in VS Code bottom-left should read **WSL: Ubuntu**.

---

## Git

```
user.name  = bekeib
user.email = bekei.balazs@gmail.com
init.defaultBranch = main
core.autocrlf = input
```

- **SSH key**: `~/.ssh/id_ed25519` — public key registered on GitHub
- **Remote hosting**: GitHub (github.com/bbekei)

---

## Project Structure

```
~/projects/
  image-dupe-manager/    ← PhotoDupe / DejaView desktop app
  adoszakerto/           ← Andrea's tax advisory site tooling (planned)
  (more to be added)
```

Each project has its own Git repo and its own `.devcontainer/` config for full environment isolation.

---

## Dev Container Standard

Every project uses **VS Code Dev Containers** backed by Docker. This ensures:
- Isolated runtimes per project (no version conflicts)
- Reproducible environments (devcontainer.json in Git)
- Clean separation between projects

### Devcontainer conventions

- Base images from `mcr.microsoft.com/devcontainers/`
- Language versions pinned explicitly (never `latest` for runtimes)
- System dependencies installed in `Dockerfile`
- Package manager caches installed via `postCreateCommand`
- Project-specific VS Code extensions declared in `devcontainer.json`

### Tauri project Dockerfile requirements
Any project using Tauri must include these apt packages:
```dockerfile
RUN apt-get update && apt-get install -y \
    libwebkit2gtk-4.1-dev \
    build-essential \
    curl \
    wget \
    file \
    libssl-dev \
    libayatana-appindicator3-dev \
    librsvg2-dev \
    libgtk-3-dev \
    libxdo-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*
```

---

## Active Projects

### image-dupe-manager (PhotoDupe / DejaView)
- **Repo**: github.com/bbekei/image-dupe-manager
- **Stack**: Tauri v2 + React + TypeScript (frontend), Python 3.11 (scanning/hashing engine)
- **Key libs**: Zustand, @tanstack/react-virtual, @tanstack/react-query, Radix UI
- **Python libs**: defined in `dejaview/requirements-dev.txt`
- **Devcontainer**: Python 3.11 base, Node 20 + Rust via features, full Tauri Linux deps
- **Storage**: SQLite, hash-only cloud sync (no full photo upload)

### adoszakerto (Andrea's tax advisory tooling)
- **Site**: adoszakerto.eu (WordPress on cPanel shared hosting)
- **DB**: `adoszake_wp741`, table prefix `wp96_`
- **Key script**: `ahb_sync.py` — CalDAV (iCloud) → AHB booking plugin sync
- **Python**: virtualenv at `/home/adoszake/virtualenv/ahb_sync/3.11/bin/python`
- **MySQL user**: `adoszake_ahb_sync` (restricted)
- **Devcontainer**: Python 3.11, no frontend stack needed

---

## Windows Reinstall Survival Guide

1. Export WSL2: `wsl --export Ubuntu D:\WSL\backups\ubuntu-YYYY-MM-DD.tar`
2. Push all Git repos to GitHub
3. Wipe C: freely — D: survives untouched
4. After reinstall: `wsl --install` then `wsl --import Ubuntu C:\WSL\Ubuntu D:\WSL\backups\ubuntu-LATEST.tar --version 2`
5. Reinstall: Docker Desktop, VS Code, Windows Terminal, PowerShell 7
6. Re-enable Docker WSL Integration for Ubuntu
7. Back to work
