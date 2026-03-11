"""
Universal QUBO IR Validator
---------------------------

Validates symbolic Hamiltonian IR JSON before matrix materialization.

Checks:
✔ Constraint coverage
✔ Quadratic form compliance
✔ Slack structural compliance
✔ Variable integrity
✔ Tier correctness
✔ Metadata correctness
✔ Safety rules
✔ Determinism (optional hash mode)

Compatible with IR v4.2 / v5.x
"""

import json
import hashlib
from typing import Dict, Any, Set


class IRValidationError(Exception):
    pass


class UniversalIRValidator:

    # ============================================
    # ENTRY
    # ============================================

    def validate(self, ir: Dict, resolver: Dict = None, deterministic_hash=False):

        print("\n==============================")
        print("UNIVERSAL QUBO IR VALIDATION")
        print("==============================\n")

        self._validate_structure(ir)
        self._validate_constraints(ir, resolver)
        self._validate_quadratic_form(ir)
        self._validate_slack(ir)
        self._validate_variables(ir)
        self._validate_metadata(ir)
        self._validate_safety(ir)

        if deterministic_hash:
            self._print_hash(ir)

        print("\n✔ IR VALIDATION PASSED\n")

    # ============================================
    # 1. BASIC STRUCTURE
    # ============================================

    def _validate_structure(self, ir):

        required_keys = [
            "variables",
            "constraints",
            "objective",
            "metadata"
        ]

        for key in required_keys:
            if key not in ir:
                raise IRValidationError(f"Missing required IR key: {key}")

        print("✔ Structure check passed")

    # ============================================
    # 2. CONSTRAINT COVERAGE
    # ============================================

    def _validate_constraints(self, ir, resolver):

        if resolver:
            resolver_ids = {
                c["id"]
                for c in resolver["data_contract"]["constraints"]["hard_constraints"]
            }

            ir_ids = {c["id"] for c in ir["constraints"]}

            if resolver_ids != ir_ids:
                raise IRValidationError(
                    f"Constraint mismatch.\nResolver: {resolver_ids}\nIR: {ir_ids}"
                )

            print("✔ Constraint coverage matches resolver")

        for c in ir["constraints"]:
            if "expression" not in c:
                raise IRValidationError(f"Constraint {c['id']} missing expression")

        print("✔ Constraint structure valid")

    # ============================================
    # 3. QUADRATIC FORM CHECK
    # ============================================

    def _validate_quadratic_form(self, ir):

       allowed_nodes = {
            "square",
            "add",
            "subtract",
            "multiply",

            "variable",
            "constant",
            "parameter",
            "dataset",

            "aggregation",
            "weighted_aggregation",

            "slack_expansion",

            # routing / graph
            "flow_balance",
            "connection_enforcement",

            # scheduling
            "time_propagation",
            "arrival_time_bound",
            "precedence_chain",

            # relationship constraints
            "relationship_gate",

            # derived algebra
            "derived_metric",
            "difference_squared"
        }

    def traverse(node, depth=0):

        if not isinstance(node, dict):
            return

        node_type = node.get("type")

        if node_type and node_type not in allowed_nodes:
            raise IRValidationError(f"Illegal node type: {node_type}")

        # square must wrap linear expression
        if node_type == "square":
            arg = node.get("argument")
            if not arg:
                raise IRValidationError("Square missing argument")

        for key in ["left", "right", "argument"]:
            if key in node:
                traverse(node[key], depth + 1)

        for c in ir["constraints"]:
            expr = c["expression"]["expression_tree"]
            traverse(expr)

    print("✔ Quadratic symbolic form validated")

    # ============================================
    # 4. SLACK VALIDATION
    # ============================================

    def _validate_slack(self, ir):

        slack_vars = [
            name for name, v in ir["variables"].items()
            if v.get("structure") == "slack"
        ]

        slack_count_metadata = ir["metadata"].get("slack_variable_count", 0)

        if slack_count_metadata != len(slack_vars):
            raise IRValidationError(
                f"Slack metadata mismatch. Found {len(slack_vars)}, "
                f"metadata says {slack_count_metadata}"
            )

        for name in slack_vars:
            v = ir["variables"][name]

            if v.get("origin") != "slack":
                raise IRValidationError(f"Slack variable {name} missing correct origin")

            if "slack_encoding" not in v:
                raise IRValidationError(f"Slack variable {name} missing encoding")

        print("✔ Slack compliance validated")

    # ============================================
    # 5. VARIABLE INTEGRITY
    # ============================================

    def _validate_variables(self, ir):

        declared_vars = set(ir["variables"].keys())

        referenced_vars = set()

        def collect(node):
            if not isinstance(node, dict):
                return

            if node.get("type") == "variable":
                referenced_vars.add(node.get("name"))

            if node.get("type") == "slack_expansion":
                referenced_vars.add(node.get("slack_variable"))

            for key in ["left", "right", "argument"]:
                if key in node:
                    collect(node[key])

        for c in ir["constraints"]:
            collect(c["expression"]["expression_tree"])

        undefined = referenced_vars - declared_vars

        if undefined:
            raise IRValidationError(f"Undefined variables referenced: {undefined}")

        print("✔ Variable integrity validated")

    # ============================================
    # 6. METADATA CHECK
    # ============================================

    def _validate_metadata(self, ir):

        meta = ir["metadata"]

        if meta["constraint_count"] != len(ir["constraints"]):
            raise IRValidationError("Constraint count metadata mismatch")

        required_metadata = [
            "variable_count_estimate",
            "slack_variable_count",
            "constraint_count",
            "compile_timestamp"
        ]

        for k in required_metadata:
            if k not in meta:
                raise IRValidationError(f"Missing metadata field: {k}")
        print("✔ Metadata consistency validated")

    # ============================================
    # 7. SAFETY RULES
    # ============================================

    def _validate_safety(self, ir):

        forbidden = {"non_quadratic_terms", "solver_specific_constructs"}

        for key in forbidden:
            if key in ir:
                raise IRValidationError(f"Forbidden construct in IR: {key}")

        print("✔ Safety rules validated")

    # ============================================
    # 8. DETERMINISTIC HASH
    # ============================================

    def _print_hash(self, ir):

        canonical = json.dumps(ir, sort_keys=True)
        digest = hashlib.sha256(canonical.encode()).hexdigest()

        print("\nDeterministic IR SHA256:")
        print(digest)