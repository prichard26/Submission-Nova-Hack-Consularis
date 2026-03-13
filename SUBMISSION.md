# Amazon Nova Hackathon — Consularis Submission

## Text description (for Devpost form)

**A brief summary of your project, its purpose, and how it leverages Amazon Nova foundation models:**

---

Mid-sized businesses—pharmacies, local chains, growing SMBs—are exactly the ones that *need* automation the most: they’re often stuck in repetitive, manual routines that make the day-to-day exhausting and scaling nearly impossible. But discovery alone costs **$5,000–$15,000** (or **$100–$250/hour**), which puts that intelligence out of reach for them. There’s a huge opportunity in that gap. Consularis uses **Amazon Nova on AWS Bedrock** to give these companies access anyway: an agent that guides them through process mapping in plain language and generates a **Company Process Intelligence Report**—key metrics, process landscape, and AI-written recommendations on what to automate and which tools to use. Nova powers the conversational BPMN editor (Aurelius), the automation analyzer, and the report narratives, so they get discovery-grade insight and a shareable PDF without the consulting price tag. Built for the Agentic AI category: one reasoning agent, one workspace, one report—for the businesses that are most stuck and least able to pay for the old way.

---

## About the project

*What inspired you, what you learned, how you built your project, and the challenges you faced.*

### Inspiration: The mid-market gap

Before any RPA or workflow automation goes live, someone has to answer: *Which processes? Which steps? What’s the ROI?* That “discovery” phase is where consulting and automation agencies charge heavily—**$5,000–$15,000** for a first engagement, **$100–$250/hour** for discovery, and mid-market projects into the **$20,000–$100,000** range. For **mid-sized companies**—pharmacies, local retail chains, growing SMBs—those numbers make automation consulting a non-starter. They simply can’t justify the upfront cost to even *explore* what to automate.

Yet these are often the businesses **most** stuck in repetitive work: manual data entry, rekeying between systems, the same routines day in and day out. That grind makes the day-to-day boring and demoralizing, and it makes growth hard—hiring more people just scales the same inefficiency. There’s a huge business opportunity in serving this segment: they need process intelligence and automation roadmaps as much as enterprises do, but the traditional consulting model leaves them behind. We wanted a tool that could give them discovery-grade intelligence anyway—map your operations in a structured way, get a report that says what to automate and why—powered by a single AI agent, without the price tag that keeps mid-market out.

We were also inspired by research on **LLM-assisted process modeling**. The MDPI paper *“BPMN Assistant: An LLM-Based Approach to Business Process Modeling”* (Licardo et al., *Appl. Sci.* 2026, 16(5), 2213) shows that large language models can effectively bridge natural language and formal process models (BPMN), reducing dependency on technical experts and accelerating digital transformation. Consularis extends that idea: we use Amazon Nova not only to create and edit process graphs via conversation but to *analyze* them and produce written narratives—executive summary, automation opportunities, and tool suggestions—so the output is both machine-readable (BPMN, metrics) and human-ready (reports, PDFs).

### What we built

Consularis is a **process intelligence** web app with three pillars:

1. **Conversational process mapping (Aurelius)**  
   Users work in a workspace (company/session), chat with an agent (Aurelius) powered by **Amazon Nova on AWS Bedrock**, and describe their processes in natural language. The agent has tools to read and update a hierarchical BPMN 2.0 graph (nodes, edges, metadata such as duration, cost, error rate, automation potential). The diagram updates live as the user and agent refine steps, owners, and automation notes. No BPMN expertise required.

2. **Automation analysis**  
   Once the graph is populated, the user can run an **Analyze** flow. A separate Nova call (analyzer) receives the full graph summary and returns markdown: which steps are strong automation candidates, which tools (e.g. n8n, Zapier, Power Automate) fit, and a short CTA to book an appointment with Consularis for implementation. All driven by Nova’s reasoning over the structured process data.

3. **Company Process Intelligence Report**  
   The **Report** aggregates computed metrics (totals, per-process stats, automation distribution, top issues) and sends them to Nova again to generate two narrative sections: an **Executive Summary** (overview, key findings, top recommendations with concrete numbers and process/step names) and **Automation opportunities** (high-potential steps, a proposed workflow, and next steps). The frontend renders this with charts (e.g. bar charts for metrics, pie charts for automation potential and current state) and supports **PDF export** for sharing with stakeholders.

The backend is **FastAPI** (Python); the frontend is **React + Vite**. Process data lives in an in-memory SQLite-backed store; BPMN is the source of truth. Nova is used in three places: the main chat agent (with tool use), the analyzer (single-turn, read-only), and the report generator (two narrative sections, each with a dedicated prompt and metrics context). We use the Bedrock Converse API and Nova foundation models (e.g. Nova Pro, Nova Lite) for all of these.

### What we learned

- **Structured tools beat free-form generation for graphs.** Letting Nova call discrete tools (`get_node`, `update_node`, `add_edge`, etc.) on a BPMN-oriented store gave us reliable, incremental updates and validation (IDs, schema) instead of fragile one-shot XML generation. This aligns with the BPMN Assistant paper’s finding that structured, incremental editing outperforms raw XML generation in reliability and latency.
- **Separating “analysis” from “editing” simplified prompts and behavior.** The main agent (Aurelius) edits the graph; the analyzer and report writer only read metrics/summaries and produce text. That separation made it easier to tune each Nova use case and avoid mixed tool-calling + long-form writing in one flow.
- **Report quality depends on context shape.** Passing compact, consistent metrics (totals, per-process, distributions, top issues) as text to Nova produced more consistent executive summaries and automation sections than dumping raw JSON. We learned to design a small “metrics context” format and to ask explicitly for concrete names and numbers in the prompts.

### Challenges we faced

- **Keeping the report and UI in sync.** The report depends on the current session graph and computed metrics. We had to ensure the frontend requested the report only when data was ready and that PDF layout (charts, sections, headers) behaved well across screen and print. We iterated on CSS (e.g. print margins, chart scaling, section breaks) so the exported PDF looked professional.
- **Balancing generality vs. domain.** Our baseline BPMN and registry are tuned to a specific domain (e.g. library/consular-style processes), but the agent and prompts are written to be adaptable. We had to avoid over-fitting prompts to one vertical while still giving Nova enough structure (e.g. automation_potential, current_state) to produce useful recommendations.
- **Tool-calling reliability.** Nova’s tool use is strong, but we had to design tool schemas and error messages so that invalid or ambiguous user requests (e.g. “change step X” when X doesn’t exist) led to clear feedback and retries rather than broken graph state. Validation in the backend after each tool call was essential.

---

## References

- **Consulting / discovery costs:** Industry pricing guides (e.g. Syntora, AutomateNexus, SILA) report automation consulting discovery at **$100–$250/hour**, with typical first engagements **$5,000–$15,000** and mid-market projects **$20,000–$100,000**. ROI timelines of 3–8 months and 25–30% productivity gains are commonly cited for well-scoped automation.
