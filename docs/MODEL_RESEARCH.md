# Model Research: Which AI Model for a Call Center Agent

Research done on 2026-10-16 to answer the PRD review's question about which AI model provider to use (question 6 in `docs/PRD_REVIEW.md`). It covers three things: how current models score on public tests built to imitate customer service work, which measures the call center industry uses to judge AI agents, and what current practice says about building one safely.

## 1. How models score on customer service tests

### The tests that matter

- **tau-bench and tau²-bench** (from Sierra, a customer service AI company) are the most widely used tests that resemble call center work. An AI model plays the agent; a second AI model plays a customer with a goal (change a flight, return an item, fix a phone plan). The agent must talk to the customer, call tools against a database, and follow a written company policy. A task passes only if the database ends up in the correct state. It has retail, airline and telecom areas.
- **tau³ (tau-knowledge)** adds a banking area where the agent must search about 700 documents to answer, which is closest to our knowledge-base part. **tau-voice** tests spoken calls with interruptions and background noise.
- **JourneyBench** (January 2026 research paper) tests whether support agents follow multi-step business policies across 703 conversations.

### Headline scores

The OpenRouter tau²-bench airline leaderboard, run on 2026-10-16, is the only one that measures every current model under the same setup and also reports cost and time per task. Selected rows (airline area, share of tasks passed):

| Model | Company | Tasks passed | Cost per task | Time per task |
|---|---|---|---|---|
| Claude Fable 5 | Anthropic | 80.0% | $0.92 | 2.1 min |
| Claude Fable 5.1 | Anthropic | 79.2% | $0.72 | 1.9 min |
| Claude Opus 5 | Anthropic | 78.7% | $0.49 | 2.1 min |
| Gemini 4 Argon | Google | 78.7% | $0.50 | 5.8 min |
| Gemini 3.7 Flash | Google | 78.3% | $0.15 | 3.1 min |
| Claude Sonnet 5.5 | Anthropic | 78.0% | $0.16 | 82 s |
| GPT-5.1 | OpenAI | 77.1% | $0.41 | 7.9 min |
| Claude Opus 5.5 | Anthropic | 75.8% | $0.33 | 2.2 min |
| Claude Haiku 5.5 | Anthropic | 75.3% | $0.012 | 1.6 min |
| GPT-5.5 | OpenAI | 75.1% | $0.49 | 2.4 min |
| GPT-6 Astra | OpenAI | 68.0% | $0.58 | 2.4 min |

On the official taubench.com site, the combined text leaderboard (retail, airline and telecom) is led by Qwen3.5 (87.9%), Gemini 3.0 Pro (85.4%) and Claude Opus 4.5 (85.3%). The document-search banking test is much harder: the leader, Qwen 3.8 Max, passes 55.2%, with Claude Opus 5 at 48.7%. Newer models are not all listed there yet.

### How to read these numbers

- **The top twenty models are within about five points of each other.** The airline area has about 50 tasks, so one task is about two points. Differences of two or three points are likely noise; the ranking near the top should not decide the choice.
- **The tests reward finishing tasks, not knowing when to stop.** None of them scores a well-judged handoff to a human as a success. The PRD values handoff over a confident wrong answer, so these scores only partly predict what matters here.
- **The document-search test is far harder than the tool tests** (about 50% against about 80%). Our knowledge-base answers are the riskiest part, whichever model is used; good retrieval and a rule to escalate when the documents do not clearly answer matter more than the model.
- **Consistency matters as much as average score.** tau-bench's authors introduced a measure called pass^k: the chance that the agent gets the same task right on every one of k tries. In the original paper a strong model passed about 61% of retail tasks once but under 25% on all eight of eight tries. A call center needs the same answer every time.
- **How the agent is built can matter more than which model.** JourneyBench found that an agent whose steps are controlled by code (it knows which stage of a policy it is in) followed policy far better than one given the whole policy in a single prompt, to the point that a small model with that structure beat a larger one without it.
- **Several leaderboard sites copy each other's numbers or accept self-reported results.** Only OpenRouter and taubench.com were used for the figures above.

### Cost for this project

Prices are per million tokens (a token is roughly three-quarters of a word), from Anthropic's published prices on 2026-10-06. The estimate assumes a six-turn conversation with about 4,000 tokens of instructions and documents sent each turn and about 200 tokens of reply, before any savings from caching.

| Model | Input / output price | One conversation | 100-conversation test run | Sorting all 420 transcripts |
|---|---|---|---|---|
| Claude Fable 5.1 | $10 / $50 | about $0.30 | about $30 | about $9 |
| Claude Opus 5.5 | $4 / $20 | about $0.12 | about $12 | about $3.50 |
| Claude Sonnet 5.5 | $2 / $10 | about $0.06 | about $6 | about $1.75 |
| Claude Haiku 5.5 | $0.10 / $0.50 | about $0.003 | about $0.30 | about $0.10 |

Prompt caching (reusing the unchanged instructions between turns) would cut the input part of these costs by roughly three-quarters.

## 2. How the industry measures AI call center agents

There is no single standard; the figures below are typical targets quoted across vendor and industry sources and should be treated as starting points.

| Measure | What it means | Typical target |
|---|---|---|
| Containment rate | Share of contacts the AI finishes without a human | 50–80%, depending on the business (the PRD asks 60–75%) |
| First contact resolution | Share of customers whose need is met on the first contact, with no repeat call | 70–85% (human call centers average about 70%) |
| Customer satisfaction (CSAT) | Share of customers rating the contact as good | above 80% |
| Repeat contact rate | Share of "resolved" customers who call back about the same thing within a few days | as low as possible; the check on containment |
| Escalation rate and escalation quality | Share handed to a human, and whether each handoff was needed and carried enough context | measured per handoff, not just counted |
| Intent recognition accuracy | Share of contacts where the AI correctly identified why the customer called | usually above 90% |
| Answer accuracy and hallucination rate | Share of answers that are correct, and share that state something not supported by the documents | hallucination as close to zero as possible |
| Average handle time and response latency | How long the contact takes, and how long each reply takes | replies within about 1–2 seconds for chat; under 1 second for voice |
| Task completion rate | Share of requested actions (such as a booking) completed correctly | as high as containment allows |

Measures for the document search on its own (the PRD's "evaluate retrieval on its own"):

| Measure | What it means |
|---|---|
| Hit rate at k | Share of test questions where a correct document appears in the top k results |
| Mean reciprocal rank | How near the top the first correct document appears, averaged over questions |
| Recall at k | Share of all the relevant documents that appear in the top k |
| Faithfulness (groundedness) | Share of the claims in an answer that the retrieved documents actually support |
| Answer relevance | Whether the answer addresses what was asked |

Two warnings recur across the sources:

- **Containment alone misleads.** A bot can show high containment because customers gave up, or because it gave a confident wrong answer that still counts as "resolved". Always report containment beside accuracy, escalation quality and, where possible, repeat contacts.
- **Faithful is not the same as correct.** An answer can match the retrieved document exactly and still be wrong if the document is out of date. This is the knowledge-base trap in this project.

## 3. Best practices for building the agent

- **Hand off for three reasons:** the AI cannot do it, the customer will not accept the AI (asks for a person), or the AI should not do it (safety, money, legal or emotional stakes). Knowing a policy is not the same as having authority to apply it.
- **Pass five things in every handoff:** who the caller is, what they want, what was already tried, any limits or constraints, and their mood. A 2026 test of live deployments found 4 of 15 handed off without passing context, forcing the customer to repeat everything.
- **Check answers against the source before they reach the customer.** The standard warning is the 2024 Air Canada case, where a tribunal held the airline liable for a refund policy its chatbot invented. Ground every factual answer in a retrieved passage and escalate when none clearly supports it.
- **Keep actions narrow and reversible.** An agent that can change the database should only be able to do the few specific actions it needs (check, book, reschedule, cancel), with checks in code rather than trusting the model.
- **Control the flow in code.** Structured flows (for example, a booking that moves through fixed steps: identify customer, choose service, offer slots, confirm) follow policy more reliably than a single long prompt, and let a smaller, faster model do the work.
- **Measure with real data, held out from tuning.** Build the test set from real transcripts in their real proportions, keep part aside until the end, have humans review a sample of 100–200 cases, and do not let the same model write and grade the answers.
- **Split satisfaction and quality numbers by who handled the contact** (AI or human), so a worsening AI experience is not hidden in an average.

## 4. What this suggests for this project

- **For the conversation itself, Claude Sonnet 5.5** sits in the top group on the customer service test, is the fastest of that group per task (82 seconds against about two minutes for the others), and costs about half of Opus 5.5. Speed matters for a caller waiting on a reply. Opus 5.5 and Fable 5.1 cost two to five times more for no measurable gain on this kind of work.
- **For sorting the 420 transcripts by call reason, Claude Haiku 5.5** at about ten cents for the whole set, with a human check of a sample.
- **For grading the agent's answers in the test set, a model from a different company** (for example Google's Gemini 3.7 Flash, which scores at the same level and costs about the same as Sonnet 5.5), so the agent does not grade its own work.
- **Design matters more than the model:** a booking flow controlled in code, an explicit rule to escalate when the retrieved documents do not clearly answer, and a measured confidence threshold.

This is a recommendation only; the choice is recorded as a decision once the author makes it.

## 5. Hosting comparison

The deciding need is the booking database: the data README says the reviewer tests the live agent against the same database, so bookings must survive restarts. Most free hosts erase their files on every restart.

| Host | Cost (2026) | Keeps the database file? | Sleeps when idle? | Notes |
|---|---|---|---|---|
| Fly.io | About $2–6 a month by memory size; disk $0.15 per GB a month | Yes, on an attached disk | No | Free allowance ended in October 2024 for new accounts; card needed after a short trial. Supports always-open connections for voice. **Chosen.** |
| Oracle Cloud Always Free | Free (2 processors, 12 GB memory) | Yes | No | Most setup work; signup capacity errors; allowance cut in mid-2026 with inconsistent enforcement. |
| Render free | Free, 750 hours a month | No; needs an outside database such as Turso (free: 5 GB, 10 million row writes a month) | After 15 minutes; 30–60 second wake-up | 512 MB memory. |
| Hugging Face Spaces | Free CPU, 16 GB memory | No | After 48 hours | One source says Docker apps became paid in 2026 (unconfirmed). |
| Railway | $5 trial, then $1 of credit a month | Yes | No | Effectively paid after the trial. |

Memory needed depends on document search: running an embedding model on the server needs about 1 GB, while a hosted embedding service (such as Voyage AI's free allowance) lets a 256 MB server work.

Hosting sources: [snapdeploy: State of Free Hosting 2026](https://snapdeploy.dev/state-of-free-hosting), [Fly.io pricing](https://fly.io/pricing.md), [sota.io pricing comparison](https://sota.io/blog/railway-vs-render-vs-fly-pricing-2026), [temps.sh: Fly.io pricing 2026](https://temps.sh/blog/fly-io-pricing-2026), [agentdeals: Turso free tier](https://agentdeals.dev/vendor/turso), [InfoQ: Oracle Cloud free tier limits](https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/), [openpython: Free Python hosting](https://openpython.org/articles/free-python-hosting).

## Sources

- [τ²-Bench Airline Leaderboard, OpenRouter (run 2026-10-16)](https://openrouter.ai/benchmarks/tau2-bench-airline)
- [τ-bench official leaderboards (taubench.com)](https://taubench.com)
- [τ-bench paper: A Benchmark for Tool-Agent-User Interaction in Real-World Domains (arXiv 2406.12045)](https://arxiv.org/pdf/2406.12045)
- [JourneyBench: Benchmarking Customer Support LLM Agents for Business-Adherence (arXiv 2601.00596)](https://arxiv.org/abs/2601.00596)
- [Tau Bench Explained (Layer3 Labs)](https://www.layer3labs.io/guides/tau-bench-explained)
- [Measuring Voice AI Agent Quality: CSAT, AHT, Containment, and the New Metrics (Twig)](https://www.twig.so/blog/voice-ai-agents-metrics-csat-aht-containment)
- [AI voice agent KPIs (CloudTalk)](https://www.cloudtalk.io/blog/ai-voice-agent-kpis/)
- [AI voice agents vs human agents: metrics comparison (Deepgram)](https://deepgram.com/learn/ai-voice-agents-vs-human-agents-metrics-comparison)
- [How to measure success of your AI agent deployment (Klink)](https://klink.cloud/post/measure-success-ai-agent-deployment)
- [Why do I have to repeat myself after an agent transfers me? The handoff cliff (Alhena)](https://alhena.ai/blog/ai-to-human-handoff/)
- [AI support agent handoff: when and how to escalate (QueryPal)](https://querypal.com/blog/ai-support-agent-handoff)
- [AI guardrails for customer service (Fin)](https://fin.ai/learn/ai-guardrails-customer-service)
- [RAG evaluation: metrics, frameworks and testing (Prem AI)](https://blog.premai.io/rag-evaluation-metrics-frameworks-testing-2026)
- [RAG evaluation metrics: a technical primer (Future AGI)](https://futureagi.substack.com/p/rag-evaluation-metrics-a-technical)
- Anthropic model prices: Claude API reference, cached 2026-10-06

## Glossary

- **Token:** the unit AI models read and write, roughly three-quarters of a word; prices are per million tokens.
- **Benchmark:** a fixed public test used to compare models.
- **Simulated customer:** a second AI model that plays the customer in a test conversation.
- **Tool call:** the model asking the program to do something, such as look up open appointment slots.
- **pass^k:** the chance an agent gets the same task right on every one of k tries; a measure of consistency.
- **Containment rate:** share of contacts the AI finishes without a human.
- **First contact resolution:** share of customers whose problem is solved on the first contact.
- **CSAT (customer satisfaction):** share of customers who rate the contact as good.
- **Hallucination:** an AI answer that states something not supported by its sources.
- **Faithfulness / groundedness:** whether an answer's claims are supported by the retrieved documents.
- **Hit rate at k, mean reciprocal rank, recall at k:** ways of scoring whether document search returned the right documents near the top.
- **Prompt caching:** reusing the unchanged start of a request so it is cheaper and faster the second time.
- **Held-out set:** test cases kept aside and not looked at while tuning, so the final measurement is fair.
- **Escalation / handoff:** passing the conversation to a human.
