# LLM Agent Evaluation Taxonomy

Updated 6 January 2026. Source: [Taxonomy of LLM Agent Evaluation](https://www.emergentmind.com/topics/taxonomy-of-llm-agent-evaluation)
on Emergent Mind.

Taxonomy of LLM Agent Evaluation is a systematic framework that categorizes
assessment along dimensions such as capability, behavior, and safety. It
integrates objective performance metrics with protocol-driven methodologies,
including scenario simulations and multi-turn evaluations. This structured
approach standardizes evaluation pipelines, fostering reproducibility and
guiding future research on robustness and scalability.

LLM agent evaluation encompasses a diverse and rapidly evolving discipline
dedicated to systematically characterizing the competencies, limitations, and
behaviors of LLM-driven autonomous systems. As LLM agents progress from static
completion engines to dynamic entities capable of adaptive planning, multi-turn
conversation, tool-mediated reasoning, and multi-agent collaboration,
traditional benchmark-driven "task success" metrics have proven inadequate for
capturing the full spectrum of emergent phenomena. In response, recent
literature delineates formal taxonomies—organizing agent evaluation along
multiple orthogonal axes such as capability, behavior, reliability, safety,
scenario specificity, and interaction modality. These frameworks aim to
standardize assessment pipelines and enable cross-framework, cross-domain robust
comparisons, while probing nuanced factors such as social cognition, consensus
dynamics, tool-use fidelity, and failure modes. The following sections
synthesize current taxonomies, metrics, protocol formalizations, and
scenario-based strategies, referencing pivotal research (Reza, 1 Oct 2025,
Zhao et al., 25 Aug 2025, Mohammadi et al., 29 Jul 2025, Ferrag et al.,
28 Apr 2025, Luo et al., 27 Mar 2025, Li, 2024, Cemri et al., 17 Mar 2025,
Guan et al., 28 Mar 2025).

## 1. High-level taxonomic dimensions of LLM agent evaluation

LLM agent evaluation frameworks consistently partition the assessment space
into distinct dimensions representing what is measured and how measurement is
performed. The two-dimensional taxonomy introduced by Mohammadi et al.
(Mohammadi et al., 29 Jul 2025) and the scenario- and role-driven frameworks of
Ferrag et al. (Ferrag et al., 28 Apr 2025) are representative.

**Evaluation objectives ("what"):**

- Agent behavior (task completion, output quality, latency)
- Agent capabilities (tool use, planning, memory, multi-agent coordination)
- Reliability (consistency, robustness to perturbation)
- Safety and alignment (fairness, harm and toxicity, compliance)

**Evaluation process ("how"):**

- Interaction mode (static, dynamic, continuous in simulators or live
  environments)
- Metric computation (code-based checks, LLM-as-judge, human-in-the-loop)
- Datasets and benchmarks (synthetic, real-world, domain-specific)
- Tooling and context (automation frameworks, leaderboards, enterprise
  sandboxes)

Protocol-centric frameworks instantiate this further with context-rich
multi-agent debates, scenario-driven simulations, and modular tool-integration
tests (Reza, 1 Oct 2025; Zhao et al., 25 Aug 2025; Ferrag et al., 28 Apr 2025).

## 2. Core metric families and formal definitions

The empirical evaluation of LLM agents is underpinned by a suite of metrics
tailored to outcome, behavioral dynamics, system-level efficiency, and
psychometric properties.

### A. Performance and task completion

Success rate (SR):

$$SR = \frac{1}{N}\sum_{i=1}^{N} \mathbb{1}\{\text{agent succeeds on task } i\}$$

Pass@k: the probability that at least one of $k$ runs succeeds.

Average reward:

$$\bar{R} = \mathbb{E}\left[\sum_{t=0}^{T} r_t\right]$$

Tool-use accuracy:

$$Acc_{tool} = \frac{\#\text{correct tool calls}}{\#\text{total calls}}$$

### B. Semantic and psychometric metrics (Reza, 1 Oct 2025)

Final stance convergence ($\mu$):

$$\mu = \frac{s_{final_1} \cdot s_{final_2}}{\lVert s_{final_1}\rVert \, \lVert s_{final_2}\rVert}$$

Total stance shift ($\Delta_{total}$):

$$\Delta_{total}^{i} = 1 - \frac{s_{initial_i} \cdot s_{final_i}}{\lVert s_{initial_i}\rVert \, \lVert s_{final_i}\rVert}$$

Semantic diversity ($D_r$):

$$D_r = \mathrm{avg}_{i<j}\left[1 - \cos(a_{r_i}, a_{r_j})\right]$$

Psychometric profiles: self-reported scales of argument confidence ($C$),
cognitive effort, empathy, and cognitive dissonance.

### C. System and human-centric metrics (Luo et al., 27 Mar 2025)

- Latency
- Throughput
- Preference rate

A multi-metric profile yields a vector-valued agent assessment, supporting
protocol-specific analytic pipelines.

| Metric category | Exemplars | Protocol and benchmark examples |
|---|---|---|
| Outcome | Success rate, average reward, pass@k | AgentBench, Multi-Judge Debate, SWE-bench |
| Dynamics | Stance shift, bias and sentiment, planning | Mind2Web, LongEval, Tree-of-Thoughts |
| Psychometrics | Final stance convergence, total stance shift, semantic diversity, psychometric profiles | Social Laboratory, persona swap protocols |
| System | Latency, throughput | ChainEval, LangChain microbenchmarks |
| Human-centric | Preference rate, SUS, empathy | ChatArena, WebGPT, HumanRankEval |

## 3. Frameworks, personas, and protocol instantiation

Agent evaluation frameworks systematically operationalize agent and moderator
personas—prompt templates conferring specific incentives or behavioral patterns
(Reza, 1 Oct 2025). This design space forms "evaluation protocols" through
factorial combinations:

- **Debater personas:** evidence-driven analyst (truth), values-focused ethicist
  (persuasion), contrarian debater (persistent disagreement)
- **Moderator personas:** neutral (impartial arbiter), consensus builder
  (agreement-fostering)
- **Debate length:** number of rounds as an independent variable

Protocols probe constructs such as consensus tendency, persona-induced
cognition, adversarial robustness, and environmental alignment. This supports
targeted experimental regimes capturing global (final stance, overall
agreement), intermediate (per-round diversity, sentiment trajectories), and
internal (psychometric states) agent phenomena.

## 4. Taxonomies for multi-agent and failure mode evaluation

Multi-agent agentic systems necessitate failure-mode-centric taxonomies. The
MAST framework (Cemri et al., 17 Mar 2025) organizes evaluation along three
top-level error categories specific to multi-agent orchestration:

- **Specification and system design:** disobey task or role specification, step
  repetition, loss of conversation history, termination unawareness
- **Inter-agent misalignment:** conversation reset, failure to clarify, task
  derailment, information withholding, ignored input, reasoning-action mismatch
- **Task verification and termination:** premature termination, incomplete
  verification, incorrect verification

Automated pipelines ("LLM-as-judge") use formal decision rules to label traces
and benchmark human annotator agreement (Cohen's $\kappa$).

## 5. Scenario-specific and benchmark-based taxonomies

Evaluation taxonomies are stratified by domain, modality, and interactivity
(Ferrag et al., 28 Apr 2025), with more than sixty benchmarks categorized across
eight groups:

- Academic and general knowledge reasoning (MMLU, BIG-Bench Extra Hard, HLE)
- Mathematical problem solving (MATH, ProcessBench, DABStep)
- Code and software engineering (Codex, ComplexFuncBench, SWE-Lancer, CASTLE)
- Factual grounding and retrieval (FACTS Grounding, CRAG)
- Domain-specific (ZODIAC, LegalAgentBench, MedAgent-Pro)
- Multimodal and embodied tasks (GAIA, EmbodiedEval, ENIGMAEVAL)
- Task selection and quality (FineTasks)
- Agentic and interactive evaluations (MultiAgentBench, τ-bench,
  Agent-as-a-Judge)

Benchmarks are mapped on modality (text, multimodal, embodied), interactivity
(static, interactive, agentic or multi-agent), and domain specificity,
pinpointing dataset gaps for future work.

## 6. Methodological taxonomies: aggregating "what" and "how"

Multi-turn conversational evaluation (Guan et al., 28 Mar 2025) employs dual
taxonomies: one for agent dimensions, one for method.

- **Evaluation goals:** task completion (TSR), response quality (BLEU, ROUGE,
  METEOR, BERTScore), user experience and safety, memory and context retention
  (context retention score), planning and tool integration (tool accuracy,
  hallucination rate)
- **Methodological families:** annotation-based (human gold), automated metrics
  (C-PMI, pairwise scoring), hybrid human-LLM, and self-judging LLM rubrics

Best-practice frameworks combine automated filtering, specialized benchmarks for
memory and tool use, and calibrated human-LLM hybrid scoring, reporting
standardized metrics.

## 7. Challenges, evolving benchmarks, and future directions

Challenges persist around consistency, cross-domain generalization,
scalability, bias in self-judging LLM evaluators, and the need for unified,
dynamic evaluation pipelines (Mohammadi et al., 29 Jul 2025; Luo et al.,
27 Mar 2025).

Key areas for future research include:

- Composite holistic metrics incorporating multi-dimensional weights according
  to application priorities
- End-to-end enterprise-grade benchmarks integrating role-based access control,
  real policies, and persistent memory
- Protocol robustness (MCP, ACP, A2A) against security and privacy threats
- Automated scaling via prompt-to-leaderboard (P2L) and adversarial stress
  protocols
- Expanded simulation of long-horizon, multi-agent, multimodal, and
  domain-specific interaction

These efforts aim to ensure rigorous, reproducible, and scalable evaluation
regimes for next-generation LLM agents, fostering robust agent deployment
across scientific, industrial, and social applications.

## References

1. *The Social Laboratory: A Psychometric Framework for Multi-Agent LLM
   Evaluation* (2025)
2. *LLM-based Agentic Reasoning Frameworks: A Survey from Methods to Scenarios*
   (2025)
3. *Evaluation and Benchmarking of LLM Agents: A Survey* (2025)
4. *From LLM Reasoning to Autonomous AI Agents: A Comprehensive Review* (2025)
5. *Large Language Model Agent: A Survey on Methodology, Applications and
   Challenges* (2025)
6. *A Review of Prominent Paradigms for LLM-Based Agents: Tool Use (Including
   RAG), Planning, and Feedback Learning* (2024)
7. *Why Do Multi-Agent LLM Systems Fail?* (2025)
8. *Evaluating LLM-based Agents for Multi-Turn Conversations: A Survey* (2025)
