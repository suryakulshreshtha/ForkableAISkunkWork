# Publishing to GitHub — macOS

Everything needed to get this repository onto
`github.com/suryakulshreshtha`, written for macOS (Apple Silicon or Intel) with
zsh. Read section 1 to know what you are shipping, then follow section 3 or 4.

---

## 1. Repository details

### Identity

| Field | Value |
|---|---|
| Repository name | `ForkablePlaywrightSelfHealer` |
| Owner | `suryakulshreshtha` |
| Default branch | `main` |
| Visibility | Public (recommended — it is a portfolio piece) |
| Licence | MIT |
| Preset remote | `https://github.com/suryakulshreshtha/ForkablePlaywrightSelfHealer.git` |
| Project folder | `PlaywrightSelfHealer/` |
| Description | Self-healing Playwright tests in Python. Plain English to UI + API tests that repair their own locators. Heuristic-first, LLM-assisted, fully offline. |
| Topics | `playwright` `self-healing-tests` `test-automation` `playwright-python` `pytest` `qa-automation` `sdet` `local-llm` `ollama` `rag` `offline-first` `e2e-testing` |

### Size and composition

| Metric | Value |
|---|---|
| Tracked files | 85 |
| Working tree | 592 KB (+ 1.3 MB `.git`) |
| Python modules (`src/`) | 35 files, 4,866 lines |
| Test files | 20 files, 1,993 lines |
| Documentation | 9 Markdown files, 717 lines |
| Knowledge corpus (RAG) | 4 Markdown files, 25 chunks |
| Commits | 8, on `main` |
| Runtime dependencies | 1 (`playwright`) — everything else is standard library |

### Code by package

| Package | Lines | Responsibility |
|---|---|---|
| `agent/` | 1,554 | Planner, healer, executor, generator, analyzer, memory, façade |
| `rag/` | 690 | Chunker, embeddings, BM25, vector store, retriever, Chroma adapter |
| `llm/` | 631 | Ollama client, deterministic rule grammar |
| `browser/` | 524 | Locator ladder, DOM snapshot, Playwright session |
| `testapp/` | 324 | Offline demo target, v2 refactor variant, JSON API |
| `reporting/` | 155 | Self-contained HTML + JSON reports |
| `visual/` | 124 | Baselines and pixel diffing |
| top-level | ~864 | `cli`, `config`, `schema`, `net_guard` |

### Commit history as it will appear

| # | SHA | Message |
|---|---|---|
| 1 | `b369a02` | Repository scaffold: MIT licence, ignore rules, overview |
| 2 | `d550995` | Packaging and configuration |
| 3 | `a51bb01` | Core: offline socket guard, settings, plan schema |
| 4 | `08f5011` | Local inference and RAG |
| 5 | `c61263d` | Agent: locator ladder, self-healing, execution, codegen, reporting |
| 6 | `ec07690` | Tests: 96 covering healing, execution, codegen and the offline guard |
| 7 | `0fb3708` | Docs, offline bootstrap scripts and CI |
| 8 | `4e1a347` | API testing, verified LLM path, namespaced memory, Docker and local CI |

SHAs change if you rewrite authorship in step 3.3 — expected, not a problem.

### What is deliberately excluded

`.gitignore` keeps these out. Confirm none slipped in before pushing.

| Excluded | Why |
|---|---|
| `.forkable/` | Runtime state: locator memory, reports, artifacts, RAG index |
| `tests/generated/` | Generated tests are build output, regenerated on demand |
| `wheelhouse/`, `ms-playwright/`, `*.tar.gz` | Offline transfer bundles, hundreds of MB |
| `.env` | Local secrets |
| `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.DS_Store` | Caches and macOS cruft |

---

## 2. macOS prerequisites

| Tool | Minimum | Install | Check |
|---|---|---|---|
| Xcode CLT | any | `xcode-select --install` | `xcode-select -p` |
| Homebrew | any | [brew.sh](https://brew.sh) | `brew --version` |
| Git | 2.30+ | `brew install git` | `git --version` |
| GitHub CLI | 2.0+ | `brew install gh` | `gh --version` |
| Python | 3.11+ | `brew install python@3.12` | `python3 --version` |
| Ollama | optional | `brew install ollama` | `ollama --version` |
| Docker Desktop | optional | `brew install --cask docker` | `docker --version` |

```bash
xcode-select --install 2>/dev/null || true
brew install git gh python@3.12
```

macOS ships an old system Git at `/usr/bin/git`. Homebrew's version comes first
on `$PATH` for Apple Silicon (`/opt/homebrew/bin`) — verify with `which git`.
If it still resolves to `/usr/bin/git`, add `eval "$(/opt/homebrew/bin/brew shellenv)"`
to `~/.zprofile`.

---

## 3. Publishing as a new repository (recommended)

### 3.1 Unpack and verify

```bash
cd ~/Developer                      # or wherever you keep projects
unzip ~/Downloads/ForkablePlaywrightSelfHealer.zip
cd ForkablePlaywrightSelfHealer/PlaywrightSelfHealer

python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,visual]"
python -m playwright install chromium     # ~150 MB, needs network once
./scripts/ci_local.sh
```

The last command runs all seven stages the GitHub workflow will run. It should
end with `CI would pass`. **Do not push until it does** — a workflow cannot be
tested before it is on GitHub, and this is the only way to find out first.

On macOS, Playwright puts browsers in `~/Library/Caches/ms-playwright`. The
first launch may take a few seconds while Gatekeeper verifies the binary.

### 3.2 Authenticate as suryakulshreshtha

```bash
gh auth login
```

Answer: **GitHub.com** → **HTTPS** → **Y** (authenticate Git with your
credentials) → **Login with a web browser**. Paste the one-time code.

```bash
gh auth status          # must show: Logged in to github.com as suryakulshreshtha
```

If a different account appears, `gh auth switch` or `gh auth logout` first.

Persist Git credentials in the macOS Keychain so you are not prompted again:

```bash
git config --global credential.helper osxkeychain
```

### 3.3 Set commit authorship

Commits are currently authored `Surya Kulshreshtha <surya@forkable.local>`, a
placeholder. GitHub attributes commits by **email**, so unless it matches an
address on your account, the history will show as an unknown author with no
avatar and no contribution graph entry.

Find your address at GitHub → Settings → Emails. If "Keep my email private" is
on, use the `ID+username@users.noreply.github.com` form shown there.

```bash
cd ~/Developer/ForkablePlaywrightSelfHealer

git config user.name  "Surya Kulshreshtha"
git config user.email "<your-github-email>"

# rewrite all 8 commits to the new author
git rebase -r --root --exec 'git commit --amend --no-edit --reset-author'

git log --pretty=format:'%h %an <%ae>' | head -3      # verify
```

If the rebase stops, `git rebase --abort` returns you to safety — nothing has
been pushed yet, so there is no risk.

### 3.4 Create the remote and push

The remote is already configured. With `gh`:

```bash
gh repo create suryakulshreshtha/ForkablePlaywrightSelfHealer \
  --public \
  --source=. \
  --remote=origin \
  --push \
  --description "Self-healing Playwright tests in Python. Plain English to UI + API tests that repair their own locators. Heuristic-first, LLM-assisted, fully offline."
```

Without `gh` — create the repo at [github.com/new](https://github.com/new)
(public, and **untick** README, .gitignore and licence, since this repo already
has all three), then:

```bash
git remote set-url origin https://github.com/suryakulshreshtha/ForkablePlaywrightSelfHealer.git
git push -u origin main
```

`git push` may open a browser for authorisation, or prompt for a password —
that password is a **personal access token**, never your account password. See
section 6 if you need one.

### 3.5 Configure the repository

```bash
gh repo edit suryakulshreshtha/ForkablePlaywrightSelfHealer \
  --add-topic playwright --add-topic self-healing-tests --add-topic test-automation \
  --add-topic playwright-python --add-topic pytest --add-topic qa-automation \
  --add-topic sdet --add-topic local-llm --add-topic ollama --add-topic rag \
  --add-topic offline-first --add-topic e2e-testing \
  --enable-issues --enable-wiki=false
```

### 3.6 Watch the first CI run

```bash
gh run watch                     # live
gh run view --log-failed         # if something breaks
```

The workflow runs a 3.11/3.12 matrix, installs Chromium, and executes the
offline suite, the egress proof, the real-browser suite and the generated-test
check. `ci_local.sh` passing locally makes green likely but not certain — CI is
Ubuntu, your machine is macOS.

---

## 4. Alternative: add to ForkedUpAIExperiments

Your existing repo indexes projects as `01-local-pdf-rag`, `02-code-review-agent`.
This would slot in as `03-`. Note that repo is a **fork** of
`kaushal9678/ai-experiments`, so commits there muddy the upstream diff — a
standalone repo is cleaner. If you still want it merged:

```bash
git clone https://github.com/suryakulshreshtha/ForkedUpAIExperiments.git
cd ForkedUpAIExperiments

cp -R ~/Developer/ForkablePlaywrightSelfHealer/PlaywrightSelfHealer ./03-playwright-ai-agent
rm -rf 03-playwright-ai-agent/.venv 03-playwright-ai-agent/.forkable

mkdir -p .github/workflows
cp ~/Developer/ForkablePlaywrightSelfHealer/.github/workflows/ci.yml .github/workflows/forkable-ci.yml
sed -i '' 's|working-directory: PlaywrightSelfHealer|working-directory: 03-playwright-ai-agent|' \
  .github/workflows/forkable-ci.yml
sed -i '' 's|PlaywrightSelfHealer/|03-playwright-ai-agent/|g' .github/workflows/forkable-ci.yml

git add . && git commit -m "Add offline Playwright AI test agent" && git push
```

`sed -i ''` — the empty argument is required by BSD sed on macOS and is a syntax
error on GNU sed. Copying a Linux one-liner is the usual way this breaks.

Then add a section to that repo's README following its existing pattern.

---

## 5. Post-push checklist

| Check | Command / where |
|---|---|
| All 85 files present | `git ls-files \| wc -l` |
| No secrets committed | `git ls-files \| grep -Ei '\.env$\|memory\.json\|token'` → empty |
| Commits attributed to you | Repo page shows your avatar on all 8 |
| CI green | Actions tab, or `gh run list` |
| README renders | Tables and code blocks intact |
| Licence detected | Sidebar shows "MIT" |
| Clone works | `git clone … /tmp/x && cd /tmp/x/PlaywrightSelfHealer && ./scripts/ci_local.sh` |

Optional hardening once CI is green:

```bash
gh api repos/suryakulshreshtha/ForkablePlaywrightSelfHealer/branches/main/protection \
  -X PUT -F required_status_checks[strict]=true \
  -F 'required_status_checks[contexts][]=test (3.12)' \
  -F enforce_admins=false -F required_pull_request_reviews=null -F restrictions=null
```

---

## 6. Personal access token (HTTPS without gh)

GitHub → Settings → Developer settings → Personal access tokens →
**Fine-grained tokens** → Generate new token.

| Setting | Value |
|---|---|
| Resource owner | `suryakulshreshtha` |
| Repository access | Only select repositories → `ForkablePlaywrightSelfHealer` |
| Permissions → Contents | Read and write |
| Permissions → Workflows | Read and write (needed to push `.github/workflows/`) |
| Expiration | 90 days |

Use the token as the password at the Git prompt. With `credential.helper
osxkeychain` set, it is stored once in Keychain Access under
`github.com`. To replace it later, delete that entry and push again.

**SSH instead**, if you prefer:

```bash
ssh-keygen -t ed25519 -C "your-github-email"
eval "$(ssh-agent -s)"

cat >> ~/.ssh/config <<'EOF'
Host github.com
  AddKeysToAgent yes
  UseKeychain yes
  IdentityFile ~/.ssh/id_ed25519
EOF

ssh-add --apple-use-keychain ~/.ssh/id_ed25519
pbcopy < ~/.ssh/id_ed25519.pub          # paste at github.com/settings/keys
ssh -T git@github.com                   # expect: Hi suryakulshreshtha!

git remote set-url origin git@github.com:suryakulshreshtha/ForkablePlaywrightSelfHealer.git
```

`UseKeychain` and `--apple-use-keychain` are macOS-only and are what stop the
passphrase prompt returning after every reboot.

---

## 7. Troubleshooting (macOS)

| Symptom | Cause | Fix |
|---|---|---|
| `xcrun: error: invalid active developer path` | CLT missing after an OS upgrade | `xcode-select --install` |
| `remote: Permission to … denied` | Wrong account cached | `gh auth switch`, or delete the `github.com` entry in Keychain Access |
| `Support for password authentication was removed` | Using account password | Use a token (section 6) |
| `refusing to merge unrelated histories` | Remote created with a README | `git push -u origin main --force` (safe: the remote has nothing you want) |
| `refusing to allow … workflow scope` | Token lacks Workflows permission | Regenerate with that permission |
| `Executable doesn't exist at ~/Library/Caches/ms-playwright/…` | Browsers not installed | `python -m playwright install chromium` |
| Chromium hangs on first launch | Gatekeeper verifying | Wait ~30 s once; or `xattr -dr com.apple.quarantine ~/Library/Caches/ms-playwright` |
| `Address already in use` on 8799 | Stale `forkable serve` | `lsof -ti:8799 \| xargs kill` |
| `zsh: command not found: forkable` | venv not active | `source .venv/bin/activate`, or use `PYTHONPATH=src python3 -m forkable_ai_agent` |
| `sed: 1: "…": invalid command code` | GNU sed syntax | BSD sed needs `sed -i ''` |
| `ollama daemon` WARN in `doctor` | Not running | `ollama serve` in another tab; harmless — the rule engine takes over |
| Visual baselines fail in CI but pass locally | macOS vs Ubuntu font rendering | Generate baselines in the Docker image (`make docker`) |
| Docker + Ollama slow on Apple Silicon | No GPU passthrough in Docker on macOS | Run Ollama on the host; the compose file already points at `host.docker.internal` |

---

## 8. One-shot script

Everything in section 3, once you have set `EMAIL`:

```bash
#!/usr/bin/env bash
set -euo pipefail
EMAIL="<your-github-email>"

cd ~/Developer/ForkablePlaywrightSelfHealer/PlaywrightSelfHealer
python3 -m venv .venv && source .venv/bin/activate
pip install -q -e ".[dev,visual]"
python -m playwright install chromium
./scripts/ci_local.sh || { echo "CI would fail — fix before pushing"; exit 1; }

cd ..
git config user.name "Surya Kulshreshtha"
git config user.email "$EMAIL"
git rebase -r --root --exec 'git commit --amend --no-edit --reset-author'

gh auth status
gh repo create suryakulshreshtha/ForkablePlaywrightSelfHealer \
  --public --source=. --remote=origin --push \
  --description "Self-healing Playwright tests in Python. Plain English to UI + API tests that repair their own locators. Heuristic-first, LLM-assisted, fully offline."

gh repo edit suryakulshreshtha/ForkablePlaywrightSelfHealer \
  --add-topic playwright --add-topic ollama --add-topic ai-agent \
  --add-topic self-healing --add-topic offline-ai --add-topic rag
gh run watch
```

Saved as `scripts/publish_macos.sh` in the project, already executable.
