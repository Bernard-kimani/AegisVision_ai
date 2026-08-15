"""
AuditLogger - immutable, append-only record of every Agent 3 guardrail decision.

JSONL over SQLite for v1: zero schema-migration risk, trivially append-only (no
UPDATE statement exists in this module), and easy for the Backtest tab / a future
compliance-review UI to stream line-by-line. A Supabase-backed AuditStore later
would implement the same read_all()/append() interface as a table insert + select.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class AuditRecord:
    timestamp: str
    symbol: str
    market_snapshot_summary: str
    llm_verdict: str                       # ACCEPT | REJECT
    llm_confidence: float
    llm_reasoning: str
    guardrail_vetoed: bool
    guardrail_veto_reason: Optional[str]
    final_action: str                      # BUY | SELL | WAIT
    final_stop_loss: Optional[float] = None    # the EA's stop, only when final_action is BUY/SELL - what was actually traded
    final_take_profit: Optional[float] = None  # the EA's target, only when final_action is BUY/SELL - what was actually traded
    entry_price: Optional[float] = None    # market price at decision time
    ea_stop_loss: Optional[float] = None       # Agent 0's proposed stop, logged regardless of the final action
    ea_take_profit: Optional[float] = None     # Agent 0's proposed target, logged regardless of the final action
    llm_stop_loss: Optional[float] = None      # Agent 2's own independent stop read (ACCEPT only)
    llm_take_profit: Optional[float] = None    # Agent 2's own independent target read (ACCEPT only) - the reward leg Agent 3 checked
    risk_reward: Optional[float] = None        # Agent 3's computed reward:risk from ea_stop_loss vs. llm_take_profit

    @staticmethod
    def now(**kwargs) -> "AuditRecord":
        kwargs.setdefault("timestamp", datetime.now().isoformat())
        return AuditRecord(**kwargs)


class AuditStore(ABC):
    @abstractmethod
    def append(self, record: AuditRecord) -> None:
        """Persist one immutable decision record."""

    @abstractmethod
    def read_all(self) -> List[AuditRecord]:
        """Read every stored record, oldest first."""


class JsonlAuditLogger(AuditStore):
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def append(self, record: AuditRecord) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def read_all(self) -> List[AuditRecord]:
        if not os.path.exists(self.path):
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(AuditRecord(**json.loads(line)))
        return records
