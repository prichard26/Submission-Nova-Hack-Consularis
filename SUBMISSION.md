# Amazon Nova Hackathon — Consularis Submission

## Text description (for Devpost form)

**A brief summary of your project, its purpose, and how it leverages Amazon Nova foundation models:**

---

Mid-sized businesses—pharmacies, local chains, growing SMBs—are exactly the ones that *need* automation the most: they’re often stuck in repetitive, manual routines that make the day-to-day exhausting and scaling nearly impossible. But discovery alone costs **$5,000–$15,000** (or **$100–$250/hour**), which puts that intelligence out of reach for them. There’s a huge opportunity in that gap. Consularis uses **Amazon Nova on AWS Bedrock** to give these companies access anyway: an agent that guides them through process mapping in plain language and generates a **Company Process Intelligence Report**—key metrics, process landscape, and AI-written recommendations on what to automate and which tools to use. Nova powers the conversational BPMN editor (Aurelius), the automation analyzer, and the report narratives, so they get discovery-grade insight and a shareable PDF without the consulting price tag. Built for the Agentic AI category: one reasoning agent, one workspace, one report—for the businesses that are most stuck and least able to pay for the old way.

---

## Inspiration

Before any RPA or workflow automation goes live, someone has to answer: *Which processes? Which steps? What’s the ROI?* That “discovery” phase is where consulting and automation agencies charge heavily—**$5,000–$15,000** for a first engagement, **$100–$250/hour** for discovery, and mid-market projects into the **$20,000–$100,000** range. For **mid-sized companies**—pharmacies, local retail chains, growing SMBs—those numbers make automation consulting a non-starter. They simply can’t justify the upfront cost to even *explore* what to automate.

Yet these are often the businesses **most** stuck in repetitive work: manual data entry, rekeying between systems, the same routines day in and day out. That grind makes the day-to-day boring and demoralizing, and it makes growth hard—hiring more people just scales the same inefficiency. There’s a huge opportunity in serving this segment: they need process intelligence and automation roadmaps as much as enterprises do, but the traditional consulting model leaves them behind. We wanted a tool that could give them discovery-grade intelligence anyway—map your operations in a structured way, get a report that says what to automate and why—powered by a single AI agent, without the price tag that keeps mid-market out.

## What it does

Consularis is a **process intelligence** web app with three pillars:

1. **Conversational process mapping (Aurelius)**
  Users can also add nodes, edges, and draw the process graph themselves in a visual, intuitive way—but that’s slow and tedious. So we offer a **conversational** path: users work in a workspace (company/session), chat with an agent (Aurelius) powered by **Amazon Nova on AWS Bedrock**, and describe their processes in plain language. The agent handles both **low-level** requests (“delete this edge”, “add a node between X and Y”) and **higher-level** ones (“please delete this flow”, “it should look more like …”, “merge these two steps”). It has tools to read and update a hierarchical BPMN 2.0 graph (nodes, edges, metadata such as duration, cost, error rate, automation potential). The diagram updates live as the user and agent refine steps, owners, and automation notes. No BPMN expertise required.
2. **Automation analysis**
  Once the graph is populated, the user can run an **Analyze** flow. A separate Nova call (analyzer) receives the full graph summary and returns markdown: which steps are strong automation candidates, which tools (e.g. n8n, Zapier, Power Automate) fit, and a short CTA to book an appointment with Consularis for implementation. All driven by Nova’s reasoning over the structured process data.
3. **Company Process Intelligence Report**
  The **Report** aggregates computed metrics (totals, per-process stats, automation distribution, top issues) and sends them to Nova to generate two narrative sections: an **Executive Summary** (overview, key findings, top recommendations with concrete numbers and process/step names) and **Automation opportunities** (high-potential steps, a proposed workflow, and next steps). The frontend renders this with charts (bar charts for metrics, pie charts for automation potential and current state) and supports **PDF export** for sharing with stakeholders.

## How we built it

The backend is **FastAPI** (Python); the frontend is **React + Vite**. Process data lives in an in-memory SQLite-backed store; BPMN 2.0 is the source of truth. We use **Amazon Nova** on AWS Bedrock in three places: the main chat agent (Aurelius) with tool use for graph edits, the analyzer (single-turn, read-only) for automation recommendations, and the report generator (two narrative sections, each with a dedicated prompt and metrics context). We call the Bedrock Converse API with Nova foundation models (e.g. Nova Pro, Nova Lite). The agent’s tools are constrained operations on the graph—`get_node`, `update_node`, `add_edge`, etc.—so Nova produces incremental, validated updates instead of raw XML; the analyzer and report writer only consume metrics and produce text, which kept prompts and behavior clean.

## Challenges we ran into

- **Keeping the report and UI in sync.** The report depends on the current session graph and computed metrics. We had to ensure the frontend requested the report only when data was ready and that PDF layout (charts, sections, headers) behaved well across screen and print. We iterated on CSS (print margins, chart scaling, section breaks) so the exported PDF looked professional.
- **Balancing generality vs. domain.** Our baseline BPMN and registry are tuned to a specific domain (e.g. library/consular-style processes), but the agent and prompts are written to be adaptable. We had to avoid over-fitting prompts to one vertical while still giving Nova enough structure (e.g. automation_potential, current_state) to produce useful recommendations.
- **Tool-calling reliability.** Nova’s tool use is strong, but we had to design tool schemas and error messages so that invalid or ambiguous user requests (e.g. “change step X” when X doesn’t exist) led to clear feedback and retries rather than broken graph state. Validation in the backend after each tool call was essential.

## Accomplishments that we're proud of

- **One agent, one workspace, one report.** A single Nova-powered flow from “describe your processes” to a shareable Company Process Intelligence Report and PDF—exactly what mid-sized businesses need without the consulting price tag.
- **Structured graph editing that works.** Giving Nova discrete tools over a BPMN-oriented store gave us reliable, incremental updates and validation instead of fragile one-shot generation; the diagram and metrics stay in sync as the user and agent refine the model.
- **Report narratives that feel tailored.** The Executive Summary and Automation opportunities sections use real process and step names and concrete numbers from the metrics, so the output reads like a real discovery deliverable, not generic advice.

## What we learned

- **Structured tools beat free-form generation for graphs.** Letting Nova call discrete tools on a BPMN-oriented store gave us reliable, incremental updates and validation (IDs, schema) instead of fragile one-shot XML generation.
- **Separating “analysis” from “editing” simplified prompts and behavior.** The main agent (Aurelius) edits the graph; the analyzer and report writer only read metrics/summaries and produce text. That separation made it easier to tune each Nova use case and avoid mixed tool-calling and long-form writing in one flow.
- **Report quality depends on context shape.** Passing compact, consistent metrics (totals, per-process, distributions, top issues) as text to Nova produced more consistent executive summaries and automation sections than dumping raw JSON. We learned to design a small “metrics context” format and to ask explicitly for concrete names and numbers in the prompts.

## What's next for Consularis

- **Domain templates and verticals.** Offer pre-built process templates (e.g. pharmacy, small retail) so mid-sized companies can start from a baseline and customize instead of mapping from scratch.
- **Persistent workspaces and collaboration.** Move from in-memory sessions to persisted storage so teams can save, share, and iterate on process models and reports over time.
- **Tighter path to implementation.** Connect the report’s automation recommendations to concrete next steps—e.g. one-click “request implementation” with Consularis or links to no-code/low-code tools (n8n, Zapier) so the report doesn’t just inform but accelerates action.

