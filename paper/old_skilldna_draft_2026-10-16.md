## Abstract

A single benchmark score hides where a coding agent is reliable and where it is not. We propose describing a Gemma 4 software-engineering agent by a **per-skill capability profile** rather than one aggregate number, and we test whether that profile carries information the aggregate score does not.

We derive skill families from the competition's code-graphs, code embeddings and issue text, using only information available *before* the agent attempts a task. Running `gemma-4-31b-it-qat-w4a16-ct` across the public tasks under three retrieval configurations (file tools, graph tools, semantic search) produces a **SkillLedger**: a per-attempt evidence record of required skills, outcome, tests, tool calls and cost. A **SkillManifest** summarizes the ledger as smoothed per-skill success rates with evidence counts and known limitations.

Our pre-registered primary hypothesis (H1) is that the skill profile predicts held-out task success beyond task-difficulty and repository baselines [RESULT: ΔAUC, 95% CI, permutation p]. Secondary hypotheses test reliability-aware abstention (H2) [RESULT: precision at 75% coverage] and skill-based routing between configurations (H3) [RESULT: routed vs. best single configuration]. We release the SkillLedger dataset, the profiling tool and a notebook that reproduces every result.

*Benchmarks tell us how an agent performed. Skill profiles tell us where it can be trusted.*

## 1. Introduction

Coding agents are moving from demonstrations into real engineering workflows, yet the way we describe them has not changed: agent, benchmark, score. A score of 78% says how often an agent succeeded on a mixed set of tasks. It does not say whether the *next* task, say an async retry bug in an unfamiliar repository, is one the agent handles well or one it should not be trusted with.

The problem is compression. Software-engineering tasks draw on different skills, and an aggregate score averages over them. Two agents with the same score can have opposite strengths (illustrative; Section 5 reports observed profiles):

| Skill family | Agent A | Agent B |
| --- | --- | --- |
| API/interface changes | 92% | 61% |
| Async/concurrency repair | 48% | 89% |
| Type/error repair | 87% | 72% |
| Test modification | 81% | 90% |
| **Overall** | **77%** | **78%** |

Practitioners already see this. A recent industry benchmark of retrieval layers for coding agents found no setup that won everywhere: plain file tools matched richer retrieval on concrete bugs, while semantic search helped most on vague tasks [14]. That study used a few tasks per condition and no statistical tests, but its conclusion, *benchmark by task shape, not just by tool*, is the question we test rigorously.

Human engineers are not hired on one number either. A résumé lists specific skills with evidence behind each. We take the metaphor seriously but implement it as data: a machine-readable SkillManifest backed by an evidence SkillLedger, where every claim traces to logged attempts.

This paper makes one narrow, falsifiable claim: **a per-skill capability profile predicts and bounds an agent's reliability on unseen tasks better than its aggregate score, after controlling for task difficulty and repository effects.** Contributions:

1. A method for deriving skill families from code-graphs and embeddings using only pre-attempt information, with semantic validation.
2. The SkillLedger, a released per-attempt dataset for Gemma 4 across [RESULT: N] tasks and three retrieval configurations.
3. A pre-registered evaluation of predictive validity (H1), abstention (H2) and routing (H3), with permutation controls.
4. A per-skill failure taxonomy derived from execution traces.

## 2. Related Work

**Agentic SWE benchmarks.** SWE-bench [1] and SWE-bench Verified [2] evaluate agents by applying a patch and running the issue's tests, reporting one pass rate. Scaffolds such as SWE-agent [3] and OpenHands [4] are compared almost entirely on that number. We keep the pass/fail signal but decompose it by skill.

**Psychometrics and IRT.** Item response theory [5] models success from a latent ability and an item difficulty, and has been applied to make LLM benchmarks more efficient [6, 7]. Our profile is a multidimensional ability estimate; we include difficulty baselines so skill effects are measured *beyond* difficulty.

**Skill libraries and capability reporting.** Voyager [8] builds an explicit library of reusable skills; model cards [9] document intended use and limitations. We combine both: a skill inventory produced from evidence rather than declared, reporting limitations as well as strengths.

**Selective prediction.** Selective classification [10] trades coverage for accuracy, evaluated by risk–coverage curves. LLM self-reported confidence is often poorly calibrated [11]. We compare skill-conditioned reliability against self-reported confidence and random abstention.

**Code graphs and retrieval for agents.** Repository graphs improve localization for coding agents [12], and practitioner benchmarks show the value of retrieval depends on task shape [14]. We use the competition's graphs and embeddings to characterize what a task *demands* before any attempt.

## 3. Method

![SkillLedger pipeline](PIPELINE_IMAGE)

The pipeline has two halves: characterizing tasks before any attempt, and building a capability profile only from logged outcomes. Skill labels never use the gold patch or the files the agent changed, so the same labels can drive abstention on a task the agent has not seen.

### 3.1 Skill families from code-graphs

For each task we build a feature vector from three pre-attempt sources: the issue text, the code-graph neighborhood of the symbols the issue names (node types, fan-in/fan-out, test coverage of the subgraph), and the provided embeddings of that neighborhood. We also score **task specificity**: whether the issue names concrete files, symbols, or error messages.

We cluster these vectors into 4–6 broad families, deliberately avoiding a deep taxonomy so per-family evidence stays large enough to estimate. Each family is validated two ways: an LLM labels every task independently of the cluster (agreement [RESULT: %]), and a human spot-checks about 20 tasks per family. Families that fail validation are merged or dropped. Each task carries soft weights w(t,k) over families, summing to one.

Before any modelling we check a key confound: if a family is dominated by one or two repositories, "skill" is really "repo". We report the family × repository table and redesign families that fail this check.

### 3.2 SkillLedger

Every attempt appends one record: task id, family weights, specificity, configuration, run index, pass/fail from the competition harness, fraction of tests passed, tool calls by category, turns, tokens and wall time. Each task is run 2–3 times per configuration, because agent outcomes are stochastic; the pass rate is the label. The ledger is the released dataset.

### 3.3 SkillManifest

For configuration c and family k, the profile entry is a Beta-smoothed success rate with its evidence count:

```
P(c,k) = (s(c,k) + α) / (n(c,k) + α + β)        n(c,k) = Σ_t w(t,k)
```

s(c,k) is the weighted number of successes; the prior counts α, β are set from the configuration's overall rate. Smoothing stops a family with 3 observations from claiming 100%. The manifest is the set of (P, n) pairs plus a known-limitations list: families whose lower credible bound falls below a threshold.

### 3.4 Reliability prediction (H1, primary)

Predicted reliability of configuration c on an unseen task t is the skill-weighted profile:

```
R(c,t) = Σ_k w(t,k) · P(c,k)
```

We compare it against difficulty-only baselines: per-repository success rate, a logistic model on difficulty features (issue length, subgraph size, files in the neighborhood, test count), and a logistic model on the raw task embedding. The primary test fits a mixed-effects logistic regression, *pass ~ difficulty + skill profile + (1 | repository)*, and asks whether adding the skill term improves held-out AUC.

### 3.5 Reliability-aware abstention (H2)

The agent attempts task t only if R(c,t) ≥ τ. Sweeping τ gives a risk–coverage curve, compared with random abstention at matched coverage and abstention on the model's own stated confidence.

### 3.6 Skill-based routing (H3)

Each task is sent to the configuration with the highest R(c,t). We compare the routed pass rate against the best single configuration and an oracle.

## 4. Experimental Setup

**Model and harness.** All runs use `gemma-4-31b-it-qat-w4a16-ct` through the competition's ADK harness and sandboxed tools, with pass/fail from the harness applying the patch and running the issue's validation tests. Hardware: [RESULT]. Median wall time per attempt: [RESULT].

**Tasks.** [RESULT: N] tasks from the public set across [RESULT: R] repositories, all listed in the released ledger.

**Configurations.** Three prompt-and-tool configurations with no adapters, mirroring the retrieval styles compared in [14]:

| Configuration | Tools exposed |
| --- | --- |
| C1 File | `read_file`, `edit_file`, `run_command` (grep and tests) |
| C2 Graph | C1 plus `get_code_subgraph`, `get_code_neighbors` |
| C3 Semantic | C1 plus `search_similar_code` |

**Pre-registration.** Hypotheses, metrics, baselines and decision thresholds were fixed and published with a timestamp before the main runs [RESULT: link]. H1 is the single primary test; H2, H3 and ablations are secondary.

**Evaluation protocol.** Repository-held-out cross-validation with [RESULT: 5] folds, so per-repository memorization cannot help the skill profile. Confidence intervals come from 1,000 bootstrap resamples over tasks.

**Evidence ladder.** Each claim must hold before the next one means anything:

| Claim | Test | Supported if |
| --- | --- | --- |
| Families differ | Mixed-effects regression, family term | p < 0.05 |
| Profiles are stable | Split-half correlation of per-family rates | r > 0.5 |
| Skill adds beyond difficulty (H1) | ΔAUC, bootstrap CI | 95% CI above 0 |
| Not an artifact of grouping | Skill labels shuffled 1,000 times | Real ΔAUC beats ≥ 95% |
| Abstention helps (H2) | Area under risk–coverage curve | CI excludes baselines |
| Routing helps (H3) | McNemar test, routed vs. best single | p < 0.05 |

**Ablations.** Families from issue text only vs. text + code-graph features; hard vs. soft family assignment.

## 5. Results

### 5.1 Skill families

[RESULT: K] families survived validation (LLM agreement [RESULT: %], human agreement [RESULT: %]).

| Family | Weighted n | Repositories | Example issue |
| --- | --- | --- | --- |
| [family] | [n] | [r] | [issue id] |

### 5.2 Observed skill profiles

[RESULT: one paragraph and a grouped bar chart of P(c,k) with intervals, one group per family, one bar per configuration.]

### 5.3 H1: predictive validity

| Predictor | AUC (mean ± sd) | Log-loss |
| --- | --- | --- |
| Overall pass rate (constant) | 0.50 | [x] |
| Per-repository rate | [x] | [x] |
| Difficulty features | [x] | [x] |
| Raw embedding | [x] | [x] |
| Skill profile R(c,t) | [x] | [x] |
| Difficulty + skill profile | [x] | [x] |

ΔAUC (difficulty + skill vs. difficulty): [RESULT, 95% CI]. Permutation test: real ΔAUC exceeds [RESULT]% of 1,000 label shuffles.

### 5.4 H2: abstention

| Coverage | Precision (skill) | Precision (random) | Precision (self-confidence) |
| --- | --- | --- | --- |
| 100% | [x] | [x] | [x] |
| 75% | [x] | [x] | [x] |
| 50% | [x] | [x] | [x] |

### 5.5 H3: routing and specificity

Best single configuration: [x]%. Skill-routed: [x]%. Oracle: [x]%. [RESULT: whether low-specificity tasks favour C3 and relational tasks favour C2, with the interaction test.]

### 5.6 Failure taxonomy and case studies

[RESULT: family × failure-mode table (wrong file located, patch does not apply, tests not run, timeout, regression introduced), plus 2–3 short cases where the aggregate score predicted success, the profile predicted failure, and the agent failed.]

## 6. Limitations

**Sample size.** Per-family evidence is modest; we report intervals throughout and treat families with n below [RESULT] as unverified.

**Labels are a model of the task.** Clustering plus validation reduces but does not remove label noise, and vaguely written issues are harder to label.

**One model, one benchmark.** Evidence comes from one quantized Gemma 4 checkpoint on the competition's Python repositories. The method is model-agnostic; these profiles are not.

**Observed capability is not learned skill.** A high rate on "async repair" means success on tasks associated with concurrency-related code, not that the model understands concurrency.

**Abstention has a cost.** Every abstained task returns to a human, so we report the full risk–coverage curve rather than one threshold.

## 7. Future Work: from profiles to SkillDNA

A predictive profile is the foundation for **SkillDNA**, a developmental system in which weak families become learning targets rather than fixed limitations:

1. **Targeted learning:** a weak family triggers curriculum tasks and feedback from a stronger model or human, followed by independent retry.
2. **Transfer and recovery tasks:** certification requires success on unseen repositories and on deliberately broken states.
3. **Independent certification:** the manifest is updated only by an evaluator that did not take part in learning, so the agent never grades itself.
4. **Skill memory vs. adapters:** retrieval over the ledger compared with family-specific LoRA adapters.
5. **Project interviews:** a short adaptive probe on the target repository to test fit before assigning work.

Each depends on H1 holding: if profiles do not predict unseen performance, a curriculum built on them has no basis.

## 8. Conclusion

A benchmark score says how often an agent succeeded. A skill profile says where it is likely to succeed next, and where it should stop and ask. We derived skill families for Gemma 4 from code-graphs using only pre-attempt information, logged every attempt in a SkillLedger, and summarized it as a SkillManifest with evidence counts and known limitations. [RESULT: H1 outcome.] [RESULT: H2 outcome.] [RESULT: H3 outcome.] The ledger, tool and notebook are released so any agent can be profiled the same way.

## Resources

- **SkillLedger dataset:** [Kaggle dataset link]
- **Reproduction notebook:** [public notebook link]
- **Code and agent configurations:** [GitHub link]
- **Pre-registration:** [timestamped link]

## References

1. Jimenez et al. *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?* ICLR 2024.
2. OpenAI. *Introducing SWE-bench Verified.* 2024.
3. Yang et al. *SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering.* NeurIPS 2024.
4. Wang et al. *OpenHands: An Open Platform for AI Software Developers as Generalist Agents.* 2024.
5. Lord and Novick. *Statistical Theories of Mental Test Scores.* 1968.
6. Polo et al. *tinyBenchmarks: Evaluating LLMs with Fewer Examples.* ICML 2024.
7. [IRT-for-LLM-evaluation paper, 2025–2026]
8. Wang et al. *Voyager: An Open-Ended Embodied Agent with Large Language Models.* 2023.
9. Mitchell et al. *Model Cards for Model Reporting.* FAT* 2019.
10. Geifman and El-Yaniv. *Selective Classification for Deep Neural Networks.* NeurIPS 2017.
11. Xiong et al. *Can LLMs Express Their Uncertainty?* ICLR 2024.
12. [Code-graph retrieval for coding agents, e.g. RepoGraph, 2024–2025]
13. Markowitz et al. *Google – The Gemma 4 Developer Agent Paper Track.* Kaggle, 2026.
14. Bansal, A. *What We Learned from Benchmarking Knowledge Bases for Coding Agents.* JioHotstar Engineering (Medium), 2026.
