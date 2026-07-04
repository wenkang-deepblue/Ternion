# Ternion

> TL;DR: Ternion is a local OpenAI-compatible gateway for Cursor that runs a three-model technical discussion, builds an evidence-based Ternion report, and can optionally execute the fix.

[![License](https://img.shields.io/badge/license-AGPL--3.0--only-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

## What Ternion Is

Ternion exists because complex engineering problems are often too important to trust to a single LLM answer.

In real codebases, one model may miss a hidden invariant, another may overlook a race condition, and a third may produce a convincing but wrong explanation. Manually switching between multiple LLMs, comparing their reasoning, checking which one is supported by real code evidence, and then turning that into a reliable fix is slow, expensive, and error-prone.

Ternion was designed to make that workflow practical inside Cursor.

It runs locally as an OpenAI-compatible gateway, sits between Cursor and model providers, and orchestrates a structured multi-model discussion behind a single model entry: `ternion-team`.

At a high level, Ternion:

- gathers real evidence from the codebase and the live request context
- asks three different models to analyze the same problem independently
- reconciles their findings through an arbiter workflow
- produces the highest-probability root-cause analysis in a structured Ternion report
- can optionally continue into code generation and code modification

The core design goal is not to be the cheapest possible assistant. The goal is to maximize the chance of finding the real root cause of difficult technical problems.

## Why It Exists

Ternion is built around a practical observation:

- LLM behavior is inherently variable
- hard bugs often require multiple perspectives before the real cause becomes clear
- the most useful answer is usually not the fastest answer, but the most evidence-backed answer

For complex issues, Ternion deliberately spends more effort up front:

- it collects more evidence
- it carries longer context
- it compares multiple analyses instead of trusting one response
- it tries to converge on the most defensible explanation before implementation

This is why Ternion is best used for difficult debugging, architecture-level failures, unclear regressions, and messy codebase problems where a single-model answer is likely to be shallow or wrong.

## Core Workflow

Ternion currently exposes one main model to Cursor:

- `ternion-team`: the full evidence-first Ternion workflow

The workflow is implemented as a staged orchestration pipeline:

1. Evidence Gathering
   Ternion inspects the codebase and request context to collect concrete evidence before analysis.
2. Divergence
   Three models analyze the problem independently.
3. Convergence
   An arbiter compares the analyses, resolves conflicts, and builds a structured Ternion report.
4. Execution
   Depending on your mode, Ternion either stops at the report or continues into implementation.
5. Review and Optimization
   Ternion can validate or refine the generated implementation before returning control.

In practice, this gives you a workflow that is closer to "multi-model technical review" than "single-model autocomplete".

## Features

### Ternion Core

- OpenAI-compatible local gateway for Cursor and other compatible clients
- evidence-first, multi-model technical discussion workflow
- three-model parallel analysis with arbiter synthesis
- structured Ternion report generation for root-cause analysis
- optional implementation path for code generation and code changes
- streaming visibility into the internal discussion process
- multimodal support through provider adapters
- fallback and recovery behavior for provider/runtime failures
- budget and usage controls
- internationalized backend and Control Panel text

### Web Control Panel

- provider API key management
- role-to-model assignment UI
- execution mode configuration
- port and local URL configuration
- usage and budget visibility
- model catalog refresh and anomaly reporting
- logs and operational diagnostics
- multi-language UI support

### Screenshot Placeholders

<!-- Screenshot placeholder: Control Panel overview -->
<!-- Screenshot placeholder: Provider API key configuration -->
<!-- Screenshot placeholder: Role-to-model assignment -->
<!-- Screenshot placeholder: Execution mode selection -->
<!-- Screenshot placeholder: Cursor settings / model setup -->
<!-- Screenshot placeholder: Cursor settings / OpenAI API Key toggle -->

## Architecture

Ternion is intentionally simple at the deployment layer and opinionated at the orchestration layer.

### Deployment Shape

- a single FastAPI process
- OpenAI-compatible API served at `/v1/*`
- Control Panel API served at `/api/*`
- bundled Control Panel UI served at `/panel`
- API docs served at `/docs`

### Internal Architecture

- FastAPI handles API compatibility, routing, and streaming
- a message-router layer adapts Cursor traffic into Ternion's internal workflow format
- LangGraph coordinates the evidence, analysis, convergence, execution, and review stages
- provider adapters normalize OpenAI, Anthropic, and Google model behavior
- a local Control Panel manages providers, role assignment, budgets, ports, and execution preferences

### High-Level Flow

```text
Cursor
  -> Ternion OpenAI-compatible gateway
  -> message routing and evidence collection
  -> three-model analysis (parallel)
  -> arbiter convergence
  -> Ternion report
  -> optional implementation / review path
  -> streamed result back to Cursor
```

## Installation

### Requirements

- Python 3.12 or newer
- at least one working provider API key
  - OpenAI API key
  - Google AI Studio / Gemini API key
  - Anthropic / Claude API key

You must configure enough providers and assign models to all required Ternion roles before Ternion can answer requests.

### Recommended

```bash
pipx install ternion
```

### Alternative

```bash
pip install ternion
```

## Run Ternion

Start Ternion:

```bash
ternion
```

On the first run after installation, Ternion will automatically ask whether you want
to customize the released backend port before it starts the service. Later runs start
the service directly with the saved configuration.

Then open:

- Control Panel: `http://127.0.0.1:<backend-port>/panel`
- API Docs: `http://127.0.0.1:<backend-port>/docs`

The released package is designed so end users do not need Node.js.

## First-Time Setup

After starting Ternion:

1. Open the Control Panel.
2. Add at least one provider API key.
3. Assign models to the required Ternion roles.
4. Choose your execution mode.
5. Save the configuration.

## Use With Cursor

### Important Constraint

Cursor's `Override OpenAI Base URL` requires a publicly reachable HTTPS URL.

`localhost` or `127.0.0.1` is not sufficient for this integration.

That means Ternion runs locally, but Cursor must connect to it through a public HTTPS tunnel.

### Public URL Options

You can expose your local Ternion server with a third-party tunnel provider such as:

- ngrok
- Cloudflare Tunnel
- Tailscale Funnel

These are third-party services with their own terms, pricing, and availability. Ternion does not bundle or distribute their binaries.

> **Security warning: use HTTP-layer tunnels only.** Ternion's access-token
> protection identifies remote traffic by the `X-Forwarded-*` headers that
> HTTP-layer tunnels and reverse proxies (ngrok, Cloudflare Tunnel, Cloud Run)
> always inject. Raw TCP port forwarders — `ssh -R`, `frp` in tcp mode,
> `socat`, generic L4 port forwarding — deliver remote traffic to loopback
> without those headers, so Ternion cannot tell it apart from your own local
> requests and the token check is silently bypassed. Do **not** expose Ternion
> to the internet through raw TCP forwarders.

### Example: ngrok

```bash
ngrok http <backend-port>
```

Then use:

```text
https://YOUR-NGROK-URL
```

as the Cursor base URL.

### Cloud Run Deployment

If you deploy Ternion on Google Cloud Run, Cursor can connect directly to the
service's public HTTPS origin instead of a local tunnel.

General flow:

1. Build and deploy the Ternion service to Cloud Run.
2. Make sure the service allows HTTPS access from the internet.
3. Copy the service origin, for example `https://your-service-xxxxx.run.app`.
4. Paste that origin into Cursor's `Override OpenAI Base URL`.
5. Do not append `/v1`.

After deploying, open the Control Panel and complete the First-Time Setup before
connecting from Cursor.

### Cursor Setup

To enable Ternion in Cursor:

1. Open `Cursor Settings -> Models -> API Keys`.
2. In the `Models` section, manually add a new model named `ternion-team`.
3. Turn on the `OpenAI API Key` toggle.
4. Enter any placeholder value in the OpenAI API key field.
5. Turn on `Override OpenAI Base URL`.
6. Paste your public tunnel URL root. Do not append `/v1`.

Example:

```text
https://your-public-url
```

<!-- Screenshot placeholder: Cursor model creation -->
<!-- Screenshot placeholder: Cursor OpenAI API Key and Override OpenAI Base URL -->

### How to Use It in Cursor

Once Cursor is configured, you use Ternion exactly from the normal chat box:

- Ask mode is suitable when you want analysis and discussion only
- Agent mode is suitable when you want Ternion to continue into implementation

From the user perspective, the workflow is simple:

1. configure Ternion once
2. enable it in Cursor
3. type your prompt in the Cursor chat box
4. let Ternion analyze the problem
5. read the Ternion report, or let it continue into code changes depending on your mode

## Practical Recommendations

### Recommended Usage Pattern

For most users, the most cost-effective pattern is:

1. use Ternion to generate a Ternion report for difficult problems
2. review the report
3. switch back to a native Cursor coding model
4. implement the report with Cursor's native Agent

This usually gives a better cost-to-value balance than using Ternion for the entire implementation phase.

### Why Ternion Can Be Expensive

Ternion is designed to maximize root-cause accuracy, not minimize token usage.

It intentionally tries to send enough evidence to support serious analysis, which means:

- longer context windows
- more tool-collected evidence
- multiple model calls
- higher latency
- higher cost

For that reason, Ternion is strongly recommended for complex problems, not routine low-cost prompting.

## Important Notes and Design Principles

1. Ternion is enabled through `Cursor Settings -> Models -> API Keys`, not through a native Cursor provider integration.
2. To use Ternion, you must manually add `ternion-team`, turn on the `OpenAI API Key` toggle, provide any placeholder API key value, and set `Override OpenAI Base URL` to your public tunnel URL.
3. Once Ternion is enabled through the OpenAI path, Cursor's native models are effectively unavailable in that configuration.
4. To switch back to Cursor native models, turn off the `OpenAI API Key` toggle. You do not need to turn off `Override OpenAI Base URL`, which helps you avoid re-entering the tunnel URL next time.
5. Ternion is optimized for difficult problems. Because it sends substantial evidence and runs a multi-model workflow, it can be costly to use for everyday requests.
6. Although Ternion Agent mode is fully usable and can directly modify code, context accumulation can make it expensive. For cost-sensitive workflows, use Ternion for report generation first, then switch to a native Cursor Agent to implement the report.
7. If the Control Panel is set to report-oriented behavior, but your current Cursor chat is in Agent mode, the effective runtime path can still move into code-changing execution. Cost-sensitive users should verify their mode before sending a request.
8. After using Ternion, remember to turn off the `OpenAI API Key` toggle in Cursor if you want to return to normal native Cursor usage.
9. You must prepare your own provider API keys. Ternion does not provide model access by itself.
10. Ternion has only recently reached its first release-ready stage. Bugs, rough edges, and missing polish should still be expected.

## Control Panel Screenshot Slots

You can place your own screenshots in the following sections:

- Control Panel home / overview
- provider key management
- role-model assignment
- execution mode settings
- port and public URL guidance
- usage / logs / diagnostics

## Troubleshooting

### Cursor cannot connect

Check the following:

- Ternion is running locally
- your tunnel URL is active
- the Cursor base URL is your public HTTPS root URL (do not append `/v1`)
- the `OpenAI API Key` toggle is on
- `ternion-team` exists in Cursor's model list

### The Control Panel does not open

Check:

- `http://127.0.0.1:<backend-port>/panel`
- whether the packaged web assets were included correctly in your installation

### Ternion returns configuration errors

Open the Control Panel and verify:

- provider API keys are configured
- required roles have assigned models
- execution mode has been saved

## Development

For local development, frontend and backend can still be run separately:

```bash
python -m ternion
cd web && npm run dev
```

That split mode is for development only. Released installations are intended to use the bundled `/panel` UI and a single `ternion` command.

## Support and Feedback

If you run into problems, please open a GitHub issue.

Bug reports, reproduction steps, screenshots, logs, and configuration details are all helpful, and I will respond as quickly as possible.

## License

Ternion is licensed under AGPL-3.0-only. See [LICENSE](LICENSE).
