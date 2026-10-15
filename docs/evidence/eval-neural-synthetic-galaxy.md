# Evaluation report -- eval_20261015T060311

- Dataset: `synthetic_galaxy`
- Samples: **18** questions across 3 synthetic documents (8 chunks indexed)
- Top-k: 5
- Embedding: `sentence-transformers:all-MiniLM-L6-v2` (384d, semantic=True)
- Answer provider: `extractive`
- Chunking: 900 chars / 150 overlap
- Fusion: dense=0.65, lexical=0.35, min_relevance=0.05
- Wall time: 1.21s

## Measured metrics

| Metric | Value |
| --- | --- |
| Recall@5 | 1.0000 |
| Precision@5 | 0.2444 |
| MRR | 1.0000 |
| Citation hit rate | 1.0000 |
| Answer rate | 1.0000 |
| Mean answer latency | 19.1 ms |
| p95 answer latency | 22.1 ms |

## Per-question results

| # | Question | Recall | P@k | RR | Citation hit | Mode | Latency (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | When did the Helios mission launch? | 1.00 | 0.20 | 1.00 | yes | extractive | 18 |
| 2 | What altitude and inclination is the observatory orbit? | 1.00 | 0.40 | 1.00 | yes | extractive | 18 |
| 3 | What is the aperture of the Wide Field Imager and how many megapixels is its focal plane array? | 1.00 | 0.20 | 1.00 | yes | extractive | 19 |
| 4 | What frequency range does the Low Frequency Spectrometer cover? | 1.00 | 0.40 | 1.00 | yes | extractive | 15 |
| 5 | What absolute pointing accuracy does the Fine Guidance Sensor deliver? | 1.00 | 0.40 | 1.00 | yes | extractive | 16 |
| 6 | How much survey data can the solid state recorder hold before downlink is required? | 1.00 | 0.20 | 1.00 | yes | extractive | 20 |
| 7 | Under what conditions does the spacecraft enter safe mode automatically? | 1.00 | 0.20 | 1.00 | yes | extractive | 19 |
| 8 | What is the nominal duration of a downlink pass and how often do passes occur? | 1.00 | 0.20 | 1.00 | yes | extractive | 20 |
| 9 | How often is calibration performed and what references are used? | 1.00 | 0.20 | 1.00 | yes | extractive | 17 |
| 10 | How long is the proprietary period before public data release? | 1.00 | 0.20 | 1.00 | yes | extractive | 16 |
| 11 | What is the primary science objective of the Helios survey? | 1.00 | 0.20 | 1.00 | yes | extractive | 18 |
| 12 | What is the total instrument mass and peak power draw? | 1.00 | 0.20 | 1.00 | yes | extractive | 21 |
| 13 | Which ground stations support the mission and where is the primary control centre? | 1.00 | 0.20 | 1.00 | yes | extractive | 21 |
| 14 | What is required to recover the observatory from safe mode? | 1.00 | 0.40 | 1.00 | yes | extractive | 19 |
| 15 | How far in advance is the observation timeline uploaded? | 1.00 | 0.20 | 1.00 | yes | extractive | 21 |
| 16 | What limiting magnitude does the Wide Field Imager reach in a 900 second exposure? | 1.00 | 0.20 | 1.00 | yes | extractive | 23 |
| 17 | What was the total mission cost through the prime phase? | 1.00 | 0.20 | 1.00 | yes | extractive | 21 |
| 18 | What temperature is the wide field detector cooled to? | 1.00 | 0.20 | 1.00 | yes | extractive | 22 |

## Methodology

Each dataset document is ingested through the production pipeline (upload -> extract -> chunk -> embed -> index) with default configuration. For every question the retriever returns the top-k chunks; a chunk counts as relevant when it contains one of the question's declared ground-truth substrings. Recall@k is the share of the question's ground-truth passages that are contained in at least one retrieved chunk (passage coverage, so it cannot exceed 1). Precision@k is the share of the k returned slots that are relevant chunks. MRR uses the rank of the first relevant chunk. Citation hit rate counts questions where at least one returned citation contains a ground-truth substring. Latency is measured around the answering call.

## Limitations

- The dataset is synthetic and small; numbers are specific to this dataset and configuration.
- Ground truth is substring containment, which is exact but shallow: a chunk can be topically relevant and still be marked irrelevant if it paraphrases the source.
- Precision@k is computed against the requested k, so a larger k mechanically lowers it.
- No comparative claim is made against any commercial system: no such comparison was run.
- Retrieval quality for the default hashing embedder is lexical; enabling the optional neural embedder changes the numbers and should be re-measured rather than assumed.

## How to reproduce

```bash
python eval/run_evaluation.py
```
