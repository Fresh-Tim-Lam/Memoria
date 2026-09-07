---
description: Memoria official showcase knowledge base — Machine Learning Intro
---

[中文](README.cn.md) | English

# Memoria Official Showcase Knowledge Base: Machine Learning Intro

An official sample knowledge base designed to **showcase Memoria end to end**: rich content, diverse typography, dense links, images and search aliases. Treat it as a product tour — open pages and follow the links.

## Quick Start

1. In Memoria, set the knowledge base root to **`docs/example/showcase/`** (this folder).
2. Start from any page and click the blue links to jump between knowledge points; the left knowledge panel highlights along.
3. Run an integrity check from the “Knowledge Check” panel, or from the command line:

```bash
python -m memoria.cli.main validate docs/example/showcase
```

## Content Map (Suggested Reading Path)

| Page | Content | Capabilities covered |
|---|---|---|
| [overview.md](./overview.md) | Machine learning overview and the three paradigms | Entry concepts, cross-page links, images |
| [supervised.md](./supervised.md) | Regression, classification, SVM, feature engineering, evaluation | Formulas, charts, code blocks |
| [tree-ensemble.md](./tree-ensemble.md) | Decision trees, random forests, GBDT | Mermaid, tables, extend relations |
| [neural-network.md](./neural-network.md) | Perceptron, MLP, activation, backprop, loss | Formulas, image attributes |
| [deep-learning.md](./deep-learning.md) | Embedding, CNN, RNN, attention, Transformer | Architecture diagrams, multi-paradigm links |
| [unsupervised.md](./unsupervised.md) | Clustering, K-Means, hierarchical clustering, PCA | Formulas, nested lists |
| [rl-intro.md](./rl-intro.md) | Reinforcement learning: MDP, Bellman equation, policy gradients | Formulas, concept chains |
| [styles-gallery.md](./styles-gallery.md) | Feature gallery: styles / images / links / search demos | Highlight, nesting, edge patterns, synonyms |

## Feature Demo Quick Reference

- **Styled text**: highlight `[[\h]]`, color `[[\c]]`, size `[[\s]]`, super/subscript, multi-level quotes & nested lists → [styles-gallery.md](./styles-gallery.md) “Text & Markup”
- **Image module**: default / fixed width / centered / right-aligned / plain title / hidden caption / Lightbox → “Image Styles”
- **Link design**: reference & extend edges, multi-target links, loops, dangling links → “Link Patterns”
- **Fuzzy search**: aliases (e.g. typing “least squares” hits linear regression) → “Search & Synonyms”

## Dangling Links Demo

The two links below point to concepts that **have no knowledge point yet**: in the preview they render grey and are not clickable (broken links), and Memoria never auto-creates empty files for dangling targets:

- [[auto-ml|AutoML]]
- [[llm-agents|LLM Agents]]

## Relation to Other Samples

`docs/example/showcase/` is the repository’s **official showcase sample** (bundled into the release at `resources/examples/`); other folders under `docs/example/` are development-time tests and personal knowledge bases (kept locally, not published).

## Maintenance Notes

- Knowledge points (KPs) and links live in `.memoria/sidecars/*.memoria.yaml`; paragraph order in the markdown must match the `range.snippet` anchors.
- After editing, run the validate command above; runtime artifacts such as `.memoria/cache/` are not committed.
