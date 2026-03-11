import json
import argparse
from pathlib import Path


# ==================================================
# HAMILTONIAN GENERATOR
# ==================================================

class HamiltonianGenerator:

    def generate(self, qubo_ir: dict) -> dict:

        objective_terms = []
        constraints = []

        # -----------------------------------------
        # Objective
        # -----------------------------------------

        objective = qubo_ir.get("objective", {})

        for term in objective.get("terms", []):

            if term["type"] == "linear":

                coeff = term["coefficient"]["value"]
                var = term["variable"]
                idx = term["index"][0]

                objective_terms.append(f"{coeff} {var}_{idx}")

        # -----------------------------------------
        # Constraints
        # -----------------------------------------

        for c in qubo_ir.get("constraints", []):

            penalty = c["penalty_weight"]["value"]

            tree = c["expression"]["expression_tree"]

            if tree["type"] == "square":

                arg = tree["argument"]

                right = arg["right"]

                if right["type"] == "constant":

                    expr = f"{penalty}(Σ_i x_i - {right['value']})²"

                elif right["type"] == "parameter":

                    expr = f"{penalty}(Σ_i,r x_i,r - {right['name']})²"

                else:
                    expr = "unknown_square"

                constraints.append(expr)

            elif tree["type"] == "pairwise_exclusion":

                over = tree["expression"]["over"]

                if over.get("entity_groups"):
                    expr = f"{penalty} Σ_sector x_i,r x_j,r"
                else:
                    expr = f"{penalty} Σ_r x_i,r x_j,r"

                constraints.append(expr)

        # -----------------------------------------
        # Build Hamiltonian
        # -----------------------------------------

        parts = []

        if objective_terms:
            parts.append(" + ".join(objective_terms))

        parts.extend(constraints)

        H = " + ".join(parts)

        return {
            "problem_id": qubo_ir.get("problem_id"),
            "phase": qubo_ir.get("phase"),
            "hamiltonian_expression": f"H(x) = {H}",
        }


# ==================================================
# FILE LOADER
# ==================================================

def load_structured_file(path: Path):

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================================================
# PIPELINE ENTRY
# ==================================================

def run_hamiltonian_generation(user_id: str) -> dict:

    base_dir = Path(__file__).parent
    result_dir = base_dir / "Result" / user_id

    qubo_ir_path = result_dir / "qubo_problem_ir.json"

    output_path = result_dir / "hamiltonian_expression.json"

    qubo_ir = load_structured_file(qubo_ir_path)

    generator = HamiltonianGenerator()

    if isinstance(qubo_ir, list):

        results = []

        for stage in qubo_ir:
            results.append(generator.generate(stage))

    else:

        results = generator.generate(qubo_ir)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"[✔] Hamiltonian JSON generated at: {output_path}")

    return results

# ==================================================
# MAIN
# ==================================================

def main():

    parser = argparse.ArgumentParser(
        description="Generate Hamiltonian from QUBO IR"
    )

    parser.add_argument(
        "--user-id",
        required=True,
        help="User ID used to locate adhoc input/output files"
    )

    args = parser.parse_args()

    run_hamiltonian_generation(args.user_id)


# ==================================================

if __name__ == "__main__":
    main()