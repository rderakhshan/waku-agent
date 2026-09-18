# LLM Agent Evaluation Taxonomy

Updated 6 January 2026.

Source: [Taxonomy of LLM Agent Evaluation](https://www.emergentmind.com/topics/taxonomy-of-llm-agent-evaluation)
on Emergent Mind.

- Taxonomy of LLM Agent Evaluation is a systematic framework that categorizes
  assessment along dimensions such as capability, behavior, and safety.
- It integrates objective performance metrics with protocol-driven
  methodologies, including scenario simulations and multi-turn evaluations.
- This structured approach standardizes evaluation pipelines, fostering
  reproducibility and guiding future research on robustness and scalability.

[LLM agent](https://www.emergentmind.com/topics/llm-agent) evaluation
encompasses a diverse and rapidly evolving discipline dedicated to
systematically characterizing the competencies, limitations, and behaviors of
LLM-driven autonomous systems. As
[LLM agents](https://www.emergentmind.com/topics/plan-then-execute-llm-agents)
progress from static completion engines to dynamic entities capable of adaptive
planning, multi-turn conversation, tool-mediated reasoning, and multi-agent
collaboration, traditional benchmark-driven "task success" metrics have proven
inadequate for capturing the full
[spectrum](https://www.emergentmind.com/topics/spectrum-6ddf6152-308c-4f1c-9dfb-589c3956f867)
of emergent phenomena. In response, recent literature delineates formal
taxonomies—organizing agent evaluation along multiple orthogonal axes such as
capability, behavior, reliability, safety, scenario specificity, and interaction
modality. These frameworks aim to standardize assessment pipelines and enable
cross-framework, cross-domain robust comparisons, while probing nuanced factors
such as social cognition, consensus dynamics, tool-use fidelity, and failure
modes. The following sections synthesize current taxonomies, metrics, protocol
formalizations, and scenario-based strategies, referencing pivotal research
([Reza, 1 Oct 2025](https://arxiv.org/abs/2510.01295),
[Zhao et al., 25 Aug 2025](https://arxiv.org/abs/2508.17692),
[Mohammadi et al., 29 Jul 2025](https://arxiv.org/abs/2507.21504),
[Ferrag et al., 28 Apr 2025](https://arxiv.org/abs/2504.19678),
[Luo et al., 27 Mar 2025](https://arxiv.org/abs/2503.21460),
[Li, 2024](https://arxiv.org/abs/2406.05804),
[Cemri et al., 17 Mar 2025](https://arxiv.org/abs/2503.13657),
[Guan et al., 28 Mar 2025](https://arxiv.org/abs/2503.22458)).

## 1. High-Level Taxonomic Dimensions of LLM Agent Evaluation

[LLM agent evaluation frameworks](https://www.emergentmind.com/topics/llm-agent-evaluation-frameworks)
consistently partition the assessment space into distinct dimensions
representing what is measured and how measurement is performed. The
two-dimensional taxonomy introduced by Mohammadi et al.
([Mohammadi et al., 29 Jul 2025](https://arxiv.org/abs/2507.21504)) and the
scenario- and role-driven frameworks of Ferrag et al.
([Ferrag et al., 28 Apr 2025](https://arxiv.org/abs/2504.19678)) are
representative.

- **Evaluation Objectives ("What")**:

  1. Agent Behavior (task completion, output quality, latency)
  2. Agent Capabilities (tool-use, planning, memory, multi-agent coordination)
  3. Reliability (consistency, robustness to perturbation)
  4. Safety & Alignment (fairness, harm/toxicity, compliance)

- **Evaluation Process ("How")**:

  1. Interaction Mode (static, dynamic, continuous in simulators or live
     environments)
  2. Metric Computation (code-based checks, LLM-as-Judge, human-in-the-loop)
  3. Datasets and Benchmarks (synthetic, real-world, domain-specific)
  4. Tooling & Context (automation frameworks, leaderboards, enterprise
     sandboxes)

This is further detailed in protocol-centric frameworks that instantiate
context-rich multi-agent debates, scenario-driven simulations, and modular
tool-integration tests ([Reza, 1 Oct 2025](https://arxiv.org/abs/2510.01295),
[Zhao et al., 25 Aug 2025](https://arxiv.org/abs/2508.17692),
[Ferrag et al., 28 Apr 2025](https://arxiv.org/abs/2504.19678)).

## 2. Core Metric Families and Formal Definitions

The empirical evaluation of
[LLM agents](https://www.emergentmind.com/topics/llm-agents) is underpinned by a
suite of metrics tailored to outcome, behavioral dynamics, system-level
efficiency, and psychometric properties.

### A. Performance and Task Completion

- **[Success Rate](https://www.emergentmind.com/topics/success-rate-sr) (SR):**

$$\text{SR} = \frac{1}{N}\sum_{i=1}^N \mathbf{1}\{\text{agent succeeds on task }i\}$$

- **Pass@k**: Probability at least one of k runs succeeds.
- **Average Reward:**

$$R = \mathbb{E}\Bigl[\sum_{t=0}^{T} r_t \Bigr]$$

- **Tool-Use Accuracy:**

$$\text{Acc}_{\rm tool} = \frac{\#\text{correct tool calls}}{\#\text{total calls}}$$

### B. Semantic and Psychometric Metrics ([Reza, 1 Oct 2025](https://arxiv.org/abs/2510.01295))

- **Final Stance Convergence ($\mu$):**

$$\mu = \frac{s^{1}_{\text{final}} \cdot s^{2}_{\text{final}}}{\|s^{1}_{\text{final}}\|\|s^{2}_{\text{final}}\|}$$

- **Total Stance Shift ($\Delta_{\text{total}}$):**

$$\Delta_{\text{total}}^{i} = 1 - \frac{s^{i}_{\text{initial}} \cdot s^{i}_{\text{final}}}{\|s^{i}_{\text{initial}}\|\|s^{i}_{\text{final}}\|}$$

- **Semantic Diversity ($D_{r}$):**

$$D_{r} = \text{avg}_{i < j}[1 - \cos(a^{i}_{r}, a^{j}_{r})]$$

- **Psychometric Profiles:** Self-reported scales of Argument
  [Confidence](https://www.emergentmind.com/topics/confidence) ($C$),
  Cognitive Effort, Empathy, Cognitive Dissonance.

### C. System and Human-Centric Metrics ([Luo et al., 27 Mar 2025](https://arxiv.org/abs/2503.21460))

- **Latency**
- **Throughput**
- **Preference Rate**

A multi-metric profile yields a vector-valued agent assessment, supporting
protocol-specific analytic pipelines (see Table below).

| Metric Category | Exemplars | Protocol/Benchmark Examples |
|---|---|---|
| Outcome | SR, Average Reward, Pass@k | AgentBench, Multi-Judge Debate, [SWE-bench](https://www.emergentmind.com/topics/swe-bench-085d928a-d773-4478-a412-44d8b11f070d) |
| Dynamics | Final Stance Convergence, bias/sentiment, planning | Mind2Web, LongEval, [Tree-of-Thoughts](https://www.emergentmind.com/topics/tree-of-thoughts-tot-318d7916-5612-4ba1-a7cf-bf707835e153) |
| Psychometrics | Argument Confidence, Cognitive Effort, Empathy, Cognitive Dissonance | Social Laboratory, [persona](https://www.emergentmind.com/topics/persona-6ba8578e-c310-45a9-a7c6-e1ad44d2695b) swap protocols |
| System | Latency, throughput | ChainEval, [LangChain](https://www.emergentmind.com/topics/langchain) microbenchmarks |
| Human-Centric | P, SUS, E | ChatArena, WebGPT, HumanRankEval |

## 3. Frameworks, Personas, and Protocol Instantiation

Agent evaluation frameworks systematically operationalize agent and moderator
personas—prompt templates conferring specific incentives or behavioral patterns
([Reza, 1 Oct 2025](https://arxiv.org/abs/2510.01295)). This design space forms
"evaluation protocols" through factorial combinations:

- **Debater Personas:** Evidence-driven analyst (truth), values-focused ethicist
  (persuasion), contrarian debater (persistent disagreement)
- **Moderator Personas:** Neutral (impartial arbiter), consensus builder
  (agreement-fostering)
- **Debate Length:** Number of rounds as an independent variable

Protocols probe constructs such as consensus tendency, persona-induced
cognition, adversarial robustness, and environmental alignment. This supports
targeted experimental regimes capturing global (final stance, overall
agreement), intermediate (per-round diversity, sentiment trajectories), and
internal (psychometric states) agent phenomena.

## 4. Taxonomies for Multi-Agent and Failure Mode Evaluation

Multi-agent [agentic systems](https://www.emergentmind.com/topics/agentic-systems)
necessitate failure-mode-centric taxonomies. The
[MAST framework](https://www.emergentmind.com/topics/mast-framework)
([Cemri et al., 17 Mar 2025](https://arxiv.org/abs/2503.13657)) organizes
evaluation along three top-level error categories specific to multi-agent
orchestration:

- **Specification & System Design:** Disobey task/role specification, step
  repetition, loss of conversation history, termination unawareness
- **Inter-Agent Misalignment:** Conversation reset, failure to clarify, task
  derailment, information withholding, ignored input, reasoning-action mismatch
- **Task Verification & Termination:** Premature termination, incomplete
  verification, incorrect verification

Automated pipelines ("LLM-as-Judge") use formal decision rules to label traces
and benchmark human annotator agreement (Cohen's $\kappa$).

## 5. Scenario-Specific and Benchmark-Based Taxonomies

Evaluation taxonomies are stratified by domain, modality, and interactivity
([Ferrag et al., 28 Apr 2025](https://arxiv.org/abs/2504.19678)), with more than
sixty benchmarks categorized across eight groups:

1. Academic/general knowledge reasoning (MMLU, BIG-Bench Extra Hard, HLE)
2. Mathematical problem solving (MATH, ProcessBench, DABStep)
3. Code and software engineering (Codex, ComplexFuncBench, SWE-Lancer, CASTLE)
4. Factual grounding and retrieval (FACTS Grounding, CRAG)
5. Domain-specific (ZODIAC, LegalAgentBench, MedAgent-Pro)
6. Multimodal and embodied tasks (GAIA, EmbodiedEval, ENIGMAEVAL)
7. Task selection and quality (FineTasks)
8. Agentic and interactive evaluations (MultiAgentBench, τ-bench,
   Agent-as-a-Judge)

Benchmarks are mapped on modality (text, multimodal, embodied), interactivity
(static, interactive, agentic/multi-agent), and domain specificity, pinpointing
dataset gaps for future work.

## 6. Methodological Taxonomies: Aggregating "What" and "How"

Multi-turn conversational evaluation
([Guan et al., 28 Mar 2025](https://arxiv.org/abs/2503.22458)) employs dual
taxonomies: one for agent dimensions, one for method.

- **Evaluation Goals:** Task completion (TSR), response quality (BLEU, ROUGE,
  METEOR, BERTScore), user experience/safety, memory/context retention (context
  retention score), planning/tool integration (tool accuracy, hallucination
  rate).
- **Methodological Families:** Annotation-based (human gold), automated metrics
  (C-PMI, pairwise scoring), hybrid human–LLM, and self-judging LLM rubrics.

Best-practice frameworks combine automated filtering, specialized benchmarks for
memory/tool use, and calibrated human–LLM hybrid scoring, reporting standardized
metrics.

## 7. Challenges, Evolving Benchmarks, and Future Directions

Challenges persist around consistency, cross-domain generalization,
scalability, bias in self-judging LLM evaluators, and the need for unified,
[dynamic evaluation](https://www.emergentmind.com/topics/dynamic-evaluation-diabench)
pipelines ([Mohammadi et al., 29 Jul 2025](https://arxiv.org/abs/2507.21504),
[Luo et al., 27 Mar 2025](https://arxiv.org/abs/2503.21460)).

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

1. [The Social Laboratory: A Psychometric Framework for Multi-Agent LLM
   Evaluation](https://arxiv.org/abs/2510.01295) (2025)
2. [LLM-based Agentic Reasoning Frameworks: A Survey from Methods to
   Scenarios](https://arxiv.org/abs/2508.17692) (2025)
3. [Evaluation and Benchmarking of LLM Agents: A
   Survey](https://arxiv.org/abs/2507.21504) (2025)
4. [From LLM Reasoning to Autonomous AI Agents: A Comprehensive
   Review](https://arxiv.org/abs/2504.19678) (2025)
5. [Large Language Model Agent: A Survey on Methodology, Applications and
   Challenges](https://arxiv.org/abs/2503.21460) (2025)
6. [A Review of Prominent Paradigms for LLM-Based Agents: Tool Use (Including
   RAG), Planning, and Feedback Learning](https://arxiv.org/abs/2406.05804)
   (2024)
7. [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657)
   (2025)
8. [Evaluating LLM-based Agents for Multi-Turn Conversations: A
   Survey](https://arxiv.org/abs/2503.22458) (2025)

## Continue Learning

1. How do current evaluation taxonomies differentiate between agent capabilities
   and interaction modalities?
2. What specific metrics best capture performance, reliability, and safety in
   LLM agent evaluations?
3. How are scenario-based protocols used to assess multi-agent coordination and
   tool integration in LLM systems?
4. What challenges exist in harmonizing diverse benchmarks and protocols across
   various LLM applications?
5. Find recent papers about LLM agent evaluation frameworks.

## Related Topics

1. [LLM-based Evaluation Method](https://www.emergentmind.com/topics/llm-based-evaluation-method)
2. [Emerging Trends in Agent Evaluation](https://www.emergentmind.com/topics/emerging-trends-in-agent-evaluation)
3. [Multi-Turn Evaluation Framework in Dialogue AI](https://www.emergentmind.com/topics/multi-turn-evaluation-framework)
4. [LLM-Based Agent Frameworks](https://www.emergentmind.com/topics/llm-based-agent-frameworks)
5. [Multi-LLM Evaluator Framework](https://www.emergentmind.com/topics/multi-llm-evaluator-framework)
6. [LLM Agent Evaluation Frameworks](https://www.emergentmind.com/topics/llm-agent-evaluation-frameworks)
7. [DevBench: Realistic Agent Evaluation](https://www.emergentmind.com/topics/devbench)
8. [Agentic Evaluations](https://www.emergentmind.com/topics/agentic-evaluations)
9. [Evaluation Agent Framework Overview](https://www.emergentmind.com/topics/evaluation-agent-framework)
10. [Automated AI Safety Evaluation](https://www.emergentmind.com/topics/automated-ai-safety-evaluation)

## Note on the source

Five formulas on the source page do not render: the psychometric scales
(cognitive effort, empathy, cognitive dissonance) and the three system and
human-centric metrics (latency, throughput, preference rate) each print the
Average Reward formula followed by a stray digit, in place of the symbol that
belongs there. The same substitution corrupts four exemplars in the metric table
and Cohen's kappa in section 4, where a formula stands where the symbol belonged.

Cohen's kappa is restored here, because its meaning is unambiguous from the
sentence. The others are given by name, because the source does not say which
symbol was lost and a guess would be worse than a gap. Everything else on this
page is reproduced as the source has it.
