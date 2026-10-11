# Demo narration

Record after the live test. Every claimed screen result must exist in the saved run. The script does not promise a particular cause, tool count, or cost.

## Spoken text

Hi! Today I'll show you a new application I built for Sunday AI Builds. It's called AI Incident Investigator.

Checkout requests return 502, and several services log errors around the same time. An engineer needs to find useful evidence and decide which explanation deserves another check.

I upload a synthetic incident file. It contains service events, spans, metrics, and deployment changes. The application parses the records and groups repeated errors. I can inspect the timeline and open source excerpts behind an event.

A deployment near the start of an incident can be relevant. It can also be a coincidence. The report needs to preserve that difference.

Before investigating, I add a reviewed historical case. It has separate sections for symptoms, root cause, resolution, and verification. Those sections become chunks in PostgreSQL. Indexing sends their redacted text to the embedding model.

Search uses text matches and embedding similarity. Reciprocal rank fusion combines the candidate ranks. I can restrict the results to the tenant, service, and environment that matter for this investigation.

The historical case gives the model a concrete comparison. A similar error message alone is not enough to reuse its conclusion. The current incident still needs its own evidence.

I start a live investigation. The model receives a selected evidence pack and relevant historical sections. It can ask local tools for more events. The activity view records requests, tool results, and short decision summaries. It does not expose the model's private thinking process.

The report separates facts, hypotheses, and missing evidence. I open a cited excerpt and check that it supports the fact. Then I inspect the proposed cause and the next diagnostic check. A useful result may be a probable cause. It may also be a statement that the evidence is insufficient.

For background execution, the application saves a queued job before the worker starts it. I can refresh the browser and retrieve the result later. If a provider call fails ambiguously, the application does not replay it automatically. A new paid attempt needs review.

The evaluation view checks report structure and citations. It does not prove the diagnosis is correct. The usage view shows provider token counts and estimated investigation cost. Embedding charges are separate from that estimate.

The application writes JSON logs per service and Python file. Prometheus receives application metrics through OpenTelemetry, and Grafana shows the dashboard. Docker verification passed 60 tests, including PostgreSQL integration.

The next test uses reviewed incidents with known outcomes. I want to see which evidence the application misses, whether historical cases improve the investigation, and how much each run costs. Those results will guide changes to retrieval and evidence selection.

## Screen cues, not spoken

- Open the structured production sample and timeline.
- Open a source excerpt and matching trace identifier.
- Import the resolved case and capture ready chunks.
- Run filtered historical search and capture the returned sections.
- Capture a completed live investigation with historical matches.
- Open a citation, hypothesis, missing-evidence item, and evaluation result.
- Show a queued job completing and its report after a refresh.
- Capture usage, cost estimate, and Grafana dashboard.
- Show a Tempo trace only after a real search returns one.
