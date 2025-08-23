from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Protocol

from anumate_crypto import canonical_json_serialize, sha256_hash


@dataclass
class Receipt:
    data: Dict[str, Any]
    checksum: str = field(init=False)

    def __post_init__(self) -> None:
        self.checksum = self._calculate_checksum()

    def _calculate_checksum(self) -> str:
        serialized_data = canonical_json_serialize(self.data)
        return sha256_hash(serialized_data).hex()

    def to_json(self) -> str:
        return json.dumps({"data": self.data, "checksum": self.checksum})


class WormWriter(Protocol):
    def write(self, receipt: Receipt) -> None:
        ...


class LocalFileSystemWormWriter:
    def __init__(self, base_path: str) -> None:
        self.base_path = base_path

    def write(self, receipt: Receipt) -> None:
        path = f"{self.base_path}/{receipt.checksum}.json"
        with open(path, "w") as f:
            f.write(receipt.to_json())
