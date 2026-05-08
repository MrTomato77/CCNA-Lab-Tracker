"""Shared constants for the lab tracker.

Anything referenced from more than one module belongs here. The frontend
mirrors these values in `public/app.js` — keep them in sync when adding a
status, category, or lab.
"""
from typing import Literal

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE        = "done"

Status = Literal["not_started", "in_progress", "done"]

STATUS_VALUES: tuple[str, ...] = (
    STATUS_NOT_STARTED,
    STATUS_IN_PROGRESS,
    STATUS_DONE,
)

STATUS_LABELS: dict[str, str] = {
    STATUS_NOT_STARTED: "Not Started",
    STATUS_IN_PROGRESS: "In Progress",
    STATUS_DONE:        "Done",
}

CATEGORIES: tuple[str, ...] = (
    "CLI & Basic",
    "Switching & VLAN",
    "Wireless",
    "Inter-VLAN & Routing",
    "HSRP & ACL",
    "NAT & DHCP",
    "Management",
    "Security & Advanced",
)

# Per-lab difficulty (1-5). Editorial data — moved here from
# scripts/extract_metadata.py so seed and the metadata sync script share one
# source. PDF extraction was unreliable across nested clip groups; the
# numbers come from the lab booklet's printed star ratings.
DIFFICULTY: dict[str, int] = {
    "LAB-01": 1, "LAB-02": 1, "LAB-03": 1, "LAB-04": 1, "LAB-05": 1,
    "LAB-06": 1, "LAB-07": 1, "LAB-08": 1, "LAB-09": 3, "LAB-10": 1,
    "LAB-11": 1, "LAB-12": 1, "LAB-13": 1, "LAB-14": 1, "LAB-15": 1,
    "LAB-16": 1, "LAB-17": 1, "LAB-18": 1, "LAB-19": 1, "LAB-20": 1,
    "LAB-21": 1, "LAB-22": 1, "LAB-23": 1, "LAB-24": 1, "LAB-25": 1,
    "LAB-26": 1, "LAB-27": 1, "LAB-28": 1, "LAB-29": 1, "LAB-30": 1,
    "LAB-31": 1, "LAB-32": 1, "LAB-33": 1, "LAB-34": 1, "LAB-35": 1,
    "LAB-36": 3, "LAB-37": 3, "LAB-38": 3, "LAB-39": 1, "LAB-40": 1,
    "LAB-41": 2, "LAB-42": 2, "LAB-43": 2, "LAB-44": 2, "LAB-45": 2,
    "LAB-46": 2, "LAB-47": 2, "LAB-48": 2, "LAB-49": 2, "LAB-50": 2,
    "LAB-51": 2,
}
