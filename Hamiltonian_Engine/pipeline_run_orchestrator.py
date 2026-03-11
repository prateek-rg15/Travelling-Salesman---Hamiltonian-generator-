"""
Pipeline Orchestrator
-----------------------------
NO domain logic
NO solver logic
NO GenAI
"""

import os
import json
from typing import Dict
from pathlib import Path

from qubo_compiler import UniversalQuboCompiler
from data_loader import DataLoader


# ==================================================
# PIPELINE ORCHESTRATOR
# ==================================================

class PipelineOrchestrator:
    """
    Coordinates the optimization pipeline after QEP creation.
    """

    def __init__(
        self,
        *,
        resolved_request: Dict,
        input_dir: str,
        output_dir: str
    ):

        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.resolved_request = resolved_request

        # --------------------------------------------------
        # Load datasets from INPUT directory
        # --------------------------------------------------

        loader = DataLoader(self.input_dir)
        datasets = loader.load_from_resolved_request(resolved_request)

        print("Datasets loaded:", list(datasets.keys()))

        # Inject datasets into request for compiler
        resolved_request["datasets"] = datasets

        # --------------------------------------------------
        # Initialize compiler
        # --------------------------------------------------

        self.qubo_compiler = UniversalQuboCompiler(resolved_request)

    # --------------------------------------------------
    # RUN PIPELINE
    # --------------------------------------------------

    def run(self, qep: Dict) -> Dict:

        problem_qubo_irs = []

        for stage in qep.get("qubo_stages", []):

            pir = self.qubo_compiler.compile(stage)

            pir["qubo_id"] = stage["qubo_id"]
            pir["phase"] = stage["phase"]

            problem_qubo_irs.append(pir)

        self._write_json("qubo_problem_ir.json", problem_qubo_irs)

        return problem_qubo_irs

    # --------------------------------------------------

    def _write_json(self, filename: str, data):

        path = self.output_dir / filename

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


# ==================================================
# PIPELINE EXECUTION ENTRY
# ==================================================

def run_execute(user_id: str, problem_type: str) -> dict:
    """
    Executes optimization run for given user_id and problem type.
    """

    base_dir = Path(__file__).parent

    # --------------------------------------------------
    # Resolve INPUT directory
    # --------------------------------------------------

    if problem_type == "travel":
        input_dir = base_dir / "Travel_Sequence_Optimization"

    elif problem_type == "portfolio":
        input_dir = base_dir / "Portfolio_Optimization"

    else:
        raise ValueError("Invalid problem type")

    # --------------------------------------------------
    # Resolve OUTPUT directory
    # --------------------------------------------------

    result_dir = base_dir / "Result" / user_id
    result_dir.mkdir(parents=True, exist_ok=True)

    print("\n[EXECUTION CONTEXT]")
    print(f"User ID      : {user_id}")
    print(f"Problem Type : {problem_type}")
    print(f"Input Dir    : {input_dir}")
    print(f"Output Dir   : {result_dir}\n")

    # --------------------------------------------------
    # Load QEP
    # --------------------------------------------------

    with open(input_dir / "qubo_execution_plan_problem.json") as f:
        qep = json.load(f)

    # --------------------------------------------------
    # Load resolved request
    # --------------------------------------------------

    with open(input_dir / "resolved_optimization_problem_request.json") as f:
        resolved_request = json.load(f)

    # --------------------------------------------------
    # Run pipeline
    # --------------------------------------------------

    orchestrator = PipelineOrchestrator(
        resolved_request=resolved_request,
        input_dir=str(input_dir),
        output_dir=str(result_dir)
    )


    result = orchestrator.run(qep)

    ir_path = result_dir / "qubo_problem_ir.json"

    print("\n====================================")
    print(" QUBO IR FILE GENERATED")
    print("====================================")
    print(f"Location: {ir_path}")

    # --------------------------------------------------
    # Ask user if Hamiltonian should be generated
    # --------------------------------------------------

    choice = input(
        "\nGenerate complete Hamiltonian JSON file? (Y/N): "
    ).strip().lower()

    if choice == "y":

        from hamiltonian_from_ir import run_hamiltonian_generation

        run_hamiltonian_generation(user_id)

        print("\n====================================")
        print(" SUCCESS")
        print("====================================")
        print("You have successfully generated:")
        print("✔ QUBO IR file")
        print("✔ Hamiltonian JSON file")

    else:

        print("\nIR generation completed.")

    return result


# ==================================================
# MAIN
# ==================================================

def main():

    print("\n====================================")
    print(" Quantum Optimization Pipeline Run")
    print("====================================\n")

    user_id = input("Enter 4-digit USER ID: ").strip()

    if not user_id.isdigit() or len(user_id) != 4:
        print("ERROR: USER ID must be a 4-digit number")
        return

    print("\nSelect Optimization Problem:")
    print("1 → Travel Sequence Optimization")
    print("2 → Portfolio Optimization")

    choice = input("Enter choice (1 or 2): ").strip()

    if choice == "1":
        problem_type = "travel"

    elif choice == "2":
        problem_type = "portfolio"

    else:
        print("Invalid selection")
        return

    try:

        result = run_execute(user_id, problem_type)

        print("\n====================================")
        print(" Pipeline Execution Completed")
        print("====================================\n")


    except Exception as e:

        print("\nPipeline execution failed:")
        print(str(e))


if __name__ == "__main__":
    main()