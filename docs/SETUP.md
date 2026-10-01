# Local setup

Supported public runtime: Linux (including Ubuntu in WSL), Python 3.11 or newer,
Node.js 22 or newer. The delivery lock uses POSIX file locking; native Windows
Python is not a supported runtime. GitHub Desktop can manage the Windows checkout;
execute the engine from Ubuntu in that checkout.

```bash
cd /path/to/your/checkout
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci --ignore-scripts
export CAREEROPS_SOURCE_DIR=examples/source
python scripts/careerops_career_ops.py self-test
python scripts/careerops_career_ops.py single --jd-file examples/jobs/data-analyst.txt --company "Glasswing Civic Archive" --position "Data Analyst" --stop-after pair_packet --no-prompt
```

The sample stops before writing. Every candidate, employer, date, metric, and job
in examples/source and examples/jobs is fictional. Example URLs use the reserved
.invalid domain and are inert. Example authority labels demonstrate the schema;
they are not evidence about a real person. The two-role example is not market research.

For real local use, configure CAREEROPS_SOURCE_DIR with your own private authority.
The default candidate/source directory is ignored and never falls back to another
checkout. Keep candidate_identity, experience_blocks, chronology, education,
provenance, tool ownership, attestations, and claim boundaries consistent. Missing
identity or authority fails closed. .env.example is a template; export the values
in your shell. The engine does not silently load it.

Full document rendering additionally needs installed Chromium, LibreOffice Writer,
and Poppler tools (pdfinfo, pdftotext, pdftohtml). Install the Playwright browser with
`npx playwright install chromium`. Fonts use system-installed families; no fonts
or handwritten signatures are bundled. A local signature image is optional via
CAREEROPS_SIGNATURE_IMAGE. Different fonts require fresh layout checks.

Writer and cloud adjudication transports use an independently installed and
explicitly authenticated inference CLI. No model calls are needed for the sample
or tests. See RUNTIME.md for the boundary before enabling generation.

For sandbox tests install your distribution's trusted bubblewrap package, then:

```bash
python tests/run_isolated.py --node "$(command -v node)"
```

The harness mounts this checkout and system runtimes, omits all home directories,
and disables network access. Test logs and runtime output stay ignored.
