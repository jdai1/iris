# Iris Topic Taxonomy Audit - 2026-06-12

Corpus audited: 2,330 fetched essays after Brown Daily Herald removal.

## Current Metadata Health

- Existing `topics[]` coverage is complete for fetched essays.
- Raw topic strings are too granular: 7,961 unique topic labels across 2,330 essays.
- Summary n-gram extraction is not a good taxonomy source because many summaries contain generic generation phrases such as "substantive essay", "essay exploring", "blog post", and "long-form essay".
- Best current signals for map/category work are: title, cleaned topics, summary after removing boilerplate wording, source/domain, and nearest-neighbor structure.

## Recommended High-Level Categories

Use these as stable, filterable, colorable map anchors. A document should usually have one primary category.

1. AI and ML
2. Software and Low-Level Tech
3. Engineering Leadership and Work
4. Productivity and Self-Improvement
5. Psychology and Rationality
6. Philosophy and Ethics
7. Money, Economics, and Markets
8. Philanthropy and Effective Altruism
9. Health, Medicine, and Bio
10. Relationships, Dating, and Social Life
11. Culture, Media, and Criticism
12. Politics, Policy, and Institutions
13. History, Anthropology, and Civilization
14. Science, Math, and Research
15. Personal Reflection and Life Narrative
16. Blogging, Writing, and Creativity
17. Fiction, Speculation, and Worldbuilding
18. Education and Learning

## Category Notes

### AI and ML

AI safety, alignment, policy, governance, ethics, LLMs, agents, machine learning practice, labs, evals, interpretability, AI and labor.

### Software and Low-Level Tech

Software engineering, systems, programming languages, infrastructure, databases, distributed systems, security, testing, observability, developer tools.

### Engineering Leadership and Work

Engineering management, staff engineering, project management, execution, mentorship, hiring, workplace communication, organizational dynamics, startup work.

### Productivity and Self-Improvement

Productivity systems, habits, focus, time management, discipline, agency, self-tracking, Beeminder, learning workflows, personal systems.

### Psychology and Rationality

Rationality, epistemics, cognitive biases, decision making, cognition, social psychology, behavioral science, incentives, signaling, mental models.

### Philosophy and Ethics

Ethics, moral philosophy, utilitarianism, decision theory, epistemology, philosophy of science, philosophy of mind, consciousness, logic, religion/philosophy.

### Money, Economics, and Markets

Monetary policy, macroeconomics, economic history, behavioral economics, markets, venture capital, personal finance, taxes, labor economics, development economics.

### Philanthropy and Effective Altruism

Effective altruism, philanthropy, charity evaluation, GiveWell, Open Philanthropy, global health, cost-effectiveness, grantmaking, longtermism.

### Health, Medicine, and Bio

Public health, COVID-19, epidemiology, clinical trials, medical evidence, mental health, neuroscience, aging research, genetics, biosecurity.

### Relationships, Dating, and Social Life

Dating advice, online dating, relationships, friendship, family, social skills, status, community, intimacy, interpersonal communication.

### Culture, Media, and Criticism

Media criticism, book reviews, literary analysis, film, television, video games, internet culture, social media, art criticism, taste.

### Politics, Policy, and Institutions

Public policy, governance, regulation, technology policy, privacy, national security, geopolitics, law, political philosophy, institutional critique.

### History, Anthropology, and Civilization

History, economic history, science history, anthropology, cultural evolution, archaeology, religion and society, linguistics, geopolitics.

### Science, Math, and Research

Mathematics, probability, statistics, physics, biology, scientific method, measurement, replication, academic incentives, research practice.

### Personal Reflection and Life Narrative

Personal essays, memoir-like writing, identity, life decisions, career narrative, college, travel, family, personal growth, year-in-review pieces.

### Blogging, Writing, and Creativity

Blogging, writing practice, note-taking, publishing, idea collection, creativity, personal websites, newsletters, archives, links posts.

### Fiction, Speculation, and Worldbuilding

Fiction, speculative fiction, fantasy, mythology, tabletop RPGs, fanfiction, alternate history, narrative design, worldbuilding.

### Education and Learning

Education, college advice, CS education, curriculum, self-studying, teaching, learning strategies, academic planning, skill acquisition.

## Implementation Recommendation

Add a controlled `Document.category` backfill using structured LLM output from `title`, `summary`, and `topics`, not full text. Use the 18 high-level categories above as enum values or a table-backed controlled vocabulary.

For the 3D viewer:

- Color by high-level category.
- Use category as the primary map anchor.
- Use raw topics only for hover/search/filter detail.
- Keep raw geometry clusters as secondary/debug metadata.

For embeddings:

- Keep full-text embeddings for search.
- Add a separate map representation built from category, cleaned topics, title, and summary.
- Do not use full extracted text for the topic map.

## Current Problems To Fix

- `topics[]` is too unconstrained and creates thousands of near-duplicates.
- Summaries contain classifier boilerplate and should not be directly mined without cleanup.
- Existing UMAP/KMeans clusters are plausible but not human-readable enough.
- Embedding projection cache is stale after embedding backfills because it keys on document id/content hash rather than embedding content/version.
