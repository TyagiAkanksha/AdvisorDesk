"""The groundedness harness: drives `seed/eval_questions.yaml` through the real chat path
(retrieval + synthesis) with injectable seams and reports answer-support/refusal metrics
(CONVENTIONS.md §2, PRD §8.1, §9.1, §10 Phase 7).
"""

from __future__ import annotations
