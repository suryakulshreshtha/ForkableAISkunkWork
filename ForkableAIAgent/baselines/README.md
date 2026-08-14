# Visual baselines

Reference screenshots for `visual_check` steps, committed so a diff is reviewable
in a pull request like any other change.

Baselines are created on first run and compared thereafter:

```bash
forkable run --file examples/nl_specs/login.txt      # creates what is missing
```

Produce and verify them in the same environment. Font rendering differs between
machines, so a baseline captured on a laptop will show spurious diffs in CI —
use the bundled Dockerfile, which pins the browser and its fonts.

To accept an intended change, delete the stale file and re-run.
