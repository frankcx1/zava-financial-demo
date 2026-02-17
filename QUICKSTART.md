# Quickstart — Intel Copilot+ PC

Get the NPU demo running on an Intel Core Ultra (Lunar Lake) device in three steps.

## What you need

- **Hardware:** Intel Core Ultra Copilot+ PC (Lunar Lake — e.g., Surface Laptop 7th Ed, Surface Pro 12th Ed)
- **OS:** Windows 11 24H2 or later
- **Network:** Internet for initial setup only (app runs fully offline after that)

## Step 1: Clone the repo

```powershell
git clone https://github.com/frankcx1/surface-npu-demo.git
cd surface-npu-demo
```

No git? Download the zip from GitHub and unzip it instead.

## Step 2: Run setup

```powershell
.\setup.ps1
```

This installs Python, Foundry Local, and pip dependencies automatically. No admin required. Takes 2-3 minutes on a fresh machine. You'll see green `[OK]` checkmarks as each step completes.

If you already have Python 3.10+ and Foundry Local installed, the script detects them and skips ahead.

## Step 3: Launch

```powershell
python npu_demo_flask.py
```

Or double-click `run.bat`.

Open **http://localhost:5000** in your browser.

## First run

On the very first launch, Foundry Local downloads the **Phi-4 Mini** model (~2 GB). You'll see `Starting Foundry Local runtime (model: phi-4-mini)...` in the terminal. This takes 1-2 minutes depending on connection speed. Subsequent launches start in seconds.

Once you see `Running on http://127.0.0.1:5000` in the terminal, the app is ready.

## Quick smoke test

1. **AI Agent tab** (default) — click **Meeting Agenda** chip. You should see the AI generate an agenda and write it to disk within 10 seconds.
2. **My Day tab** — click **Brief Me**. The AI reads demo calendar, emails, and tasks, then produces an executive briefing (~45 seconds).
3. **Auditor tab** — pick **Contract / Legal Review** and click **Analyze Demo NDA**. Structured risk analysis with escalation card.
4. **Auditor tab** — pick **Marketing / Campaign Review** and click **Review: Risky Campaign Brief**. Claims scan, AI-driven risk assessment, CELA verdict.

## The airplane mode moment

Toggle **Go Offline** in the sidebar footer (or turn on actual Airplane Mode). Repeat any demo above. Everything still works — the AI never needed the cloud.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `foundry` not recognized | Close and reopen your terminal after setup.ps1 so PATH refreshes |
| Model download hangs | Check network. If behind a proxy, Foundry Local needs direct HTTPS access |
| `Connection refused` on first launch | Foundry Local is still starting — wait 15 seconds and refresh |
| App starts but responses are slow | First inference after model load takes ~15s. Subsequent calls are faster |
| `ModuleNotFoundError: foundry_local` | Wrong package. Run `pip install foundry-local-sdk` (not `foundry-local`) |
