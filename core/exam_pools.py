"""CCNA Cert Empire exam-pool taxonomy.

The source document organizes its ~990 questions into 4 exam pools (A/B/C/D),
which correspond 1:1 to topics 1-4 (Topic 1 == Pool A, Topic 2 == Pool B, ...).
The quiz module filters questions by pool; `POOL_ALL` is a synthetic value
meaning "no pool filter".
"""
from typing import Literal

POOL_A = "A"
POOL_B = "B"
POOL_C = "C"
POOL_D = "D"
POOL_ALL = "ALL"

Pool = Literal["A", "B", "C", "D"]
SessionPool = Literal["A", "B", "C", "D", "ALL"]

POOL_VALUES: tuple[str, ...] = (POOL_A, POOL_B, POOL_C, POOL_D)
SESSION_POOL_VALUES: tuple[str, ...] = (*POOL_VALUES, POOL_ALL)

POOL_LABELS: dict[str, str] = {
    POOL_A:   "Exam Pool A",
    POOL_B:   "Exam Pool B",
    POOL_C:   "Exam Pool C",
    POOL_D:   "Exam Pool D",
    POOL_ALL: "All Pools",
}

TOPIC_TO_POOL: dict[int, str] = {
    1: POOL_A,
    2: POOL_B,
    3: POOL_C,
    4: POOL_D,
}
