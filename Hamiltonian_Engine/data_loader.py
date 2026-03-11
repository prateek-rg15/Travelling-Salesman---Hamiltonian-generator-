import csv
from typing import Dict, List
from pathlib import Path


class CsvDataSource:

    def __init__(self, file_path: Path | str):
        self.file_path = Path(file_path)

    def load(self) -> List[Dict]:

        if not self.file_path.exists():
            raise FileNotFoundError(f"Missing data file: {self.file_path}")

        with open(self.file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]


class DataLoader:

    def __init__(self, base_dir: Path | str):
        self.base_dir = Path(base_dir)

    def load_from_resolved_request(self, resolved_request: Dict) -> Dict[str, List[Dict]]:

        datasets = {}

        data_contract = resolved_request.get("data_contract", {})
        required_files = data_contract.get("required_csv_files", [])

        for file_spec in required_files:

            file_name = file_spec["file_name"]

            file_path = self.base_dir / file_name

            source = CsvDataSource(file_path)

            datasets[file_name] = source.load()

        return datasets