"""
Universal QUBO Compiler v4.3
-----------------------------

Fully Hamiltonian-complete symbolic compiler.

NEW IN v4.3
✔ Index completeness invariant (S3)
✔ Successor consistency invariant (S4)

Patch v4.3.1
✔ Runtime parameter loading from parameters.csv
✔ Structural index resolution using runtime parameters

All previous v4.2 functionality retained.
"""

import os
import json
import copy
import math
from typing import Dict, List
from datetime import datetime

# ================= VALIDATOR =================
try:
    from universal_qubo_ir_validator import UniversalIRValidator, IRValidationError
except ImportError:
    raise ImportError("ir_validator.py must exist in the same directory.")

# ==================================================
# TIER WEIGHTS
# ==================================================

TIER_WEIGHTS = {
    "T0_STRUCTURAL": 10000.0,
    "T1_FEASIBILITY": 1000.0,
    "T2_OPERATIONAL": 100.0,
    "T3_OBJECTIVE": 1.0
}

# ==================================================
# FILE LOADER
# ==================================================

def load_json(filename: str) -> Dict:

    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)

    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing required file: {filename}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================================================
# UNIVERSAL COMPILER
# ==================================================

class UniversalQuboCompiler:

    def __init__(self, resolved_request: Dict):

        self.resolved_request = resolved_request
        self.semantic_root = resolved_request.get("data_contract", resolved_request)

        self.constraint_tiers = resolved_request.get("constraint_tiers", {})
        self.numeric_scale_cfg = self.semantic_root.get("numeric_scale_normalization", {})
        self.datasets = resolved_request.get("datasets", {})
        print("Datasets available:", self.datasets.keys())
        # NEW — runtime parameters from parameters.csv
        self.runtime_parameters = self._load_runtime_parameters()
        
        self.parameter_references = set()

        self.slack_counter = 0
        
        # initialize metadata
        self._reset()
        # safe metadata update
        self.metadata["runtime_parameter_count"] = len(self.runtime_parameters)

    # --------------------------------------------------

    def _reset(self):

        self.variables = {}
        self.constraints = []
        self.objective_terms = []
        self.parameters = []

        self.metadata = {
            "normalization_applied": False,
            "slack_variable_count": 0,
            "variable_count_estimate": 0,
            "slack_total_bit_count": 0,
            "flow_constraints_present": False,
            "temporal_constraints_present": False,
            "precedence_constraints_present": False,
            "structural_indices_resolved": False
        }

    # ==================================================
    # RUNTIME PARAMETER LOADER
    # ==================================================

    def _load_runtime_parameters(self) -> Dict:
        """
        Extract runtime parameters from parameters.csv dataset.

        Enforces:
        - parameters.csv presence when required_parameters exist
        - all required parameters are provided
        - no unknown parameters are supplied
        """

        print("Datasets available:", self.datasets.keys())

        dataset = self.datasets.get("parameters.csv")

        required_params = {
            p["name"]
            for p in self.semantic_root.get("required_parameters", [])
        }

        # --------------------------------------------------
        # parameters.csv required if parameters declared
        # --------------------------------------------------

        if required_params and not dataset:
            raise RuntimeError(
                "parameters.csv is required because required_parameters are declared."
            )

        if not dataset:
            return {}

        params = {}

        for row in dataset:

            name = row.get("parameter_name")
            value = row.get("parameter_value")

            if name is None:
                raise RuntimeError(
                    "parameters.csv row missing 'parameter_name'"
                )

            if value is None:
                raise RuntimeError(
                    f"Parameter '{name}' missing value in parameters.csv"
                )

            # --------------------------------------------------
            # Numeric casting
            # --------------------------------------------------

            try:
                value = float(value)
                if value.is_integer():
                    value = int(value)
            except Exception:
                raise RuntimeError(
                    f"Parameter '{name}' must be numeric. Got '{value}'."
                )

            params[name] = value

        # --------------------------------------------------
        # Validate required parameters present
        # --------------------------------------------------

        missing = required_params - set(params.keys())

        if missing:
            raise RuntimeError(
                f"parameters.csv missing required parameters: {missing}"
            )

        # --------------------------------------------------
        # Validate no unknown parameters supplied
        # --------------------------------------------------

        unknown = set(params.keys()) - required_params

        if unknown:
            raise RuntimeError(
                f"parameters.csv contains unknown parameters: {unknown}"
            )

        print("Datasets params:", params)
        return params

    # ==================================================
    # ENTRY
    # ==================================================
    
    def compile(self, stage: Dict):

        self._reset()

        self._declare_variables()
        self._declare_parameters()

        self._expand_entity_groups()
        self._expand_derived_metrics()
        self._resolve_structural_indices()
        self._validate_csv_schema()
        self._resolve_dataset_roles()

        # Structural validation
        self._validate_index_symmetry(stage)

        self._apply_permutation_rules(stage)

        # Invariant S3
        self._validate_index_completeness()

        # -------------------------------------------------
        # Constraint compilation
        # -------------------------------------------------

        for constraint in stage.get("constraints", []):
            self._compile_constraint(constraint)

        # -------------------------------------------------
        # Objective compilation
        # -------------------------------------------------

        objective = stage.get("objective")

        if objective:
            self._compile_objective(objective)

        # Pairwise objective (covariance / interaction)
        self._compile_pairwise_objective()

        # -------------------------------------------------
        # Routing successor expansion (SAFE)
        # -------------------------------------------------

        structure = stage.get("structure_hints") or {}

        if (
            structure.get("ordering_required")
            and structure.get("ordering_type") == "succession"
        ):

            scope = structure.get("ordering_scope", {})

            if isinstance(scope, dict) and scope.get("position_index"):
                self._expand_successor_coupling()

        # -------------------------------------------------
        # Invariant S4
        # -------------------------------------------------

        self._validate_successor_consistency()

        # Relationship gating
        self._compile_relationship_gating(stage)

        self.metadata["structural_indices_resolved"] = True

        ir = self._emit_ir(stage)
        self._validate_parameter_consistency()
        
        print(f"\nIR VALIDATION for {stage['qubo_id']}")
        self._validate_ir(ir)

        return ir    
    
    def _expand_successor_coupling(self):

        dv = self.semantic_root["decision_variables"]["symbol"]
        dv_def = self.semantic_root.get("decision_variables", {})

        # ------------------------------------------------
        # Ensure decision variable has ordered position index
        # ------------------------------------------------
        indexing = dv_def.get("indexing", [])

        has_position_index = any(
            idx.get("structural_index") == "position" or idx.get("entity") == "position"
            for idx in indexing
        )

        if not has_position_index:
            return

        # ------------------------------------------------
        # Prevent duplicate successor coupling terms
        # ------------------------------------------------
        if any(term.get("id") == "routing_successor_coupling" for term in self.objective_terms):
            return

        expr = {
            "type": "successor_coupling",
            "variable": dv,
            "successor_offset": 1
        }

        self.objective_terms.append({
            "id": "routing_successor_coupling",
            "type": "quadratic",
            "applies_to": {"variable": dv},
            "interaction": expr
        })

        # mark routing presence
        self.metadata["flow_constraints_present"] = True
    
    # ==================================================
    # NEW INVARIANT S3
    # ==================================================

    def _validate_index_completeness(self):

        for vname, vdef in self.variables.items():

            if vdef.get("structure") != "indexed":
                continue

            index_sets = vdef.get("index_sets", [])

            if not index_sets:
                raise RuntimeError(
                    f"Variable '{vname}' declared indexed but no index_sets defined."
                )

            for idx in index_sets:
                if "name" not in idx:
                    raise RuntimeError(
                        f"Variable '{vname}' has incomplete index definition."
                    )

    # ==================================================
    # NEW INVARIANT S4
    # ==================================================

    def _validate_successor_consistency(self):

        structural = self.semantic_root.get("structural_indices", [])

        ordered_indices = [
            s["name"]
            for s in structural
            if s.get("type") == "ordered"
        ]

        if not ordered_indices:
            return

        interaction = self.semantic_root.get("interaction")

        if not interaction:
            return

        if interaction.get("enabled"):

            vars_used = interaction.get("variables", [])

            if len(vars_used) != 2:
                raise RuntimeError(
                    "Routing interaction must reference exactly two variables."
                )

    # ==================================================
    # STRUCTURAL INDEX EXPANSION
    # ==================================================

    def _resolve_structural_indices(self):

        structural = self.semantic_root.get("structural_indices", [])

        self.structural_index_sets = {}

        for idx in structural:

            name = idx.get("name")
            size_rule = idx.get("size_rule")

            if size_rule is None:
                continue

            # size_rule must reference runtime parameter
            if isinstance(size_rule, (int, float)):
                raise RuntimeError(
                    f"Structural index '{name}' uses numeric size_rule. "
                    "size_rule must reference a runtime parameter."
                )

            self.parameter_references.add(size_rule)

            value = self.runtime_parameters.get(size_rule)


            if value is None:
                raise RuntimeError(
                    f"Parameter '{size_rule}' required for structural index '{name}' "
                    f"not found in parameters.csv"
                )

            self.structural_index_sets[name] = list(range(1, int(value) + 1))


    # ==================================================
    # DATASET ROLE RESOLUTION
    # ==================================================

    def _resolve_dataset_roles(self):

        """
        Maps dataset_role → dataset source.
        Used for weighted aggregations and relationship lookups.
        """

        
        role_map = self.semantic_root.get("dataset_roles") or {}

        self.dataset_role_map = {}

        for role, dataset_name in role_map.items():

            if dataset_name not in self.datasets:
                raise RuntimeError(
                    f"Dataset role '{role}' references missing dataset '{dataset_name}'."
                )

            self.dataset_role_map[role] = self.datasets[dataset_name]



    # ==================================================
    # CSV SCHEMA VALIDATION
    # ==================================================

    def _validate_csv_schema(self):

        """
        Ensures datasets contain required columns defined in template.
        """

        schema = self.semantic_root.get("required_csv_files", [])

        for file_spec in schema:

            dataset_name = file_spec["file_name"]
            fields = file_spec.get("fields", [])

            dataset = self.datasets.get(dataset_name)

            if dataset is None:
                raise RuntimeError(
                    f"Required dataset '{dataset_name}' not provided."
                )

            if len(dataset) == 0:
                continue

            row = dataset[0]

            for field in fields:

                if field not in row:
                    raise RuntimeError(
                        f"Dataset '{dataset_name}' missing required column '{field}'."
                    )
    # ==================================================
    # INDEX SYMMETRY VALIDATION
    # ==================================================

    def _validate_index_symmetry(self, stage):

        """
        Ensures constraint aggregation axes match decision variable indices.
        """

        dv = self.semantic_root["decision_variables"]

        declared_indices = [
            idx.get("entity") or idx.get("structural_index")
            for idx in dv.get("indexing", [])
        ]

        constraints = stage.get("constraints", [])

        for c in constraints:

            # Safety guard
            if not isinstance(c, dict):
                continue

            agg = c.get("aggregation", {})
            axes = agg.get("over", {})

            entity_axes = axes.get("entities", [])
            structural_axes = axes.get("structural_indices", [])

            used = entity_axes + structural_axes

            for axis in used:

                if axis not in declared_indices:

                    raise RuntimeError(
                        f"Constraint '{c.get('id')}' references index '{axis}' "
                        f"not declared in decision variable."
                    )


    # ==================================================
    # PERMUTATION CLASS HANDLING
    # ==================================================

    def _apply_permutation_rules(self, stage):

        """
        Converts permutation class declarations into equality constraints.
        """

        dv = self.semantic_root.get("decision_variables", {})
        cardinality_class = dv.get("cardinality_class")

        if cardinality_class != "permutation":
            return

        variable = dv["symbol"]

        expr = self.square(
            self.subtract(
                self.aggregate(variable),
                self.constant(1)
            )
        )

        self._append_constraint(
            "permutation_exact_one",
            TIER_WEIGHTS["T0_STRUCTURAL"],
            expr
        )

    # ==================================================
    # SLACK
    # ==================================================

    import math

    def _declare_slack_variable(self, upper_bound=None, index_sets=None):

        slack_name = f"slack_{self.slack_counter}"
        self.slack_counter += 1

        bit_length = None
        auto_sized = True

        # ------------------------------------------------
        # Only compute slack size if bound is numeric
        # ------------------------------------------------
        if isinstance(upper_bound, (int, float)):

            if upper_bound < 0:
                raise RuntimeError(
                    f"Invalid slack upper bound: {upper_bound}"
                )

            # minimum one bit
            bit_length = max(1, math.ceil(math.log2(upper_bound + 1)))

            self.metadata["slack_total_bit_count"] += bit_length
            auto_sized = False

        # ------------------------------------------------
        # Resolve slack index sets from constraint scope
        # ------------------------------------------------
        resolved_indices = []

        if index_sets:

            for entity in index_sets.get("entities", []):
                resolved_indices.append({
                    "name": entity,
                    "kind": "entity"
                })

            for sidx in index_sets.get("structural_indices", []):
                resolved_indices.append({
                    "name": sidx,
                    "kind": "structural"
                })

        # ------------------------------------------------
        # Register slack variable
        # ------------------------------------------------

        self.variables[slack_name] = {
            "primitive": "binary",
            "structure": "slack",
            "origin": "slack",
            "domain": {
                "lower": 0,
                "upper": upper_bound
            },
            "index_sets": resolved_indices,
            "slack_encoding": {
                "type": "binary_weighted",
                "bit_length": bit_length,
                "upper_bound": upper_bound,
                "auto_sized": auto_sized,
                "expansion_status": "sized" if not auto_sized else "pending"
            }
        }

        self.metadata["slack_variable_count"] += 1
        self.metadata["variable_count_estimate"] += 1

        return slack_name
    # ==================================================
    # PARAMETERS
    # ==================================================

    def _declare_parameters(self):

        for p in self.semantic_root.get("required_parameters", []):

            self.parameters.append({
                "name": p["name"],
                "mode": "runtime",
                "value": None
            })


    def _expand_entity_groups(self):

        groups = self.semantic_root.get("entity_groups") or {}

        for gname, gdef in groups.items():

            entity = gdef.get("entity")
            attr = gdef.get("defined_by_attribute")

            if entity not in self.datasets:
                continue

            partitions = {}

            for row in self.datasets[entity]:

                key = row.get(attr)

                partitions.setdefault(key, []).append(row)

            gdef["resolved_groups"] = partitions

    # ==================================================
    # CONSTRAINT DISPATCH
    # ==================================================

    def _compile_constraint(self, constraint):

        # ------------------------------
        # Safety guard
        # ------------------------------
        if not isinstance(constraint, dict):
            raise RuntimeError(f"Invalid constraint structure: {constraint}")

        # ------------------------------
        # Validate constraint axes
        # Ensures constraint indices are
        # within decision variable space
        # ------------------------------
        self._validate_constraint_axes(constraint)

        # ------------------------------
        # Validate aggregation projection
        # Aggregation exists under lhs
        # ------------------------------
        lhs = constraint.get("lhs")

        if isinstance(lhs, dict) and lhs.get("aggregation"):
            self._validate_index_projection(constraint)

        cid = constraint.get("id", f"constraint_{len(self.constraints)}")
        tier = self._resolve_tier(cid)

        weight = TIER_WEIGHTS[tier]

        # ------------------------------------------------
        # Direct expression tree (already compiled form)
        # ------------------------------------------------
        if "expression_tree" in constraint:

            self._append_constraint(
                cid,
                weight,
                constraint["expression_tree"]
            )

            return

        # ------------------------------------------------
        # Universal algebraic constraint support
        # (lhs relation rhs)
        # ------------------------------------------------
        if "lhs" in constraint and "relation" in constraint and "rhs" in constraint:

            lhs_expr = constraint["lhs"]
            relation = constraint["relation"]
            rhs_value = self._extract_rhs_value(constraint)

            expr = self._compile_algebraic(lhs_expr, relation, rhs_value, constraint)

            self._append_constraint(cid, weight, expr)

            return

        # ------------------------------------------------
        # Typed constraint dispatch (legacy / specialized)
        # ------------------------------------------------
        ctype = constraint.get("type")

        dispatch = {
            "cardinality": self._compile_cardinality,
            "budget": self._compile_weighted_sum,
            "capacity": self._compile_weighted_sum,
            "exclusivity": self._compile_exclusivity,
            "flow": self._compile_flow,
            "temporal": self._compile_temporal,
            "routing": self._compile_routing,
            "precedence": self._compile_precedence,
            "assignment": self._compile_assignment,
            "inequality_le": self._compile_inequality_le
        }

        if ctype not in dispatch:

            raise RuntimeError(
                f"Unsupported constraint type '{ctype}' "
                f"in constraint {cid}"
            )

        dispatch[ctype](constraint, weight)
    
    def _validate_constraint_axes(self, constraint):

        dv = self.semantic_root["decision_variables"]

        dv_axes = {
            idx.get("entity") or idx.get("structural_index")
            for idx in dv.get("indexing", [])
        }

        # check quantifier
        q = constraint.get("quantifier", {})

        q_axes = set(
            q.get("entities", []) +
            q.get("structural_indices", [])
        )

        if not q_axes.issubset(dv_axes):

            raise RuntimeError(
                f"Constraint '{constraint.get('id')}' "
                f"uses axes {q_axes} outside decision variable axes {dv_axes}"
            )
    
    
    def _compile_algebraic(self, lhs_expr, relation, rhs_value, constraint):

        lhs_expr = self._resolve_expression(lhs_expr)

        rhs_const = (
            self.parameter(rhs_value)
            if isinstance(rhs_value, str)
            else self.constant(rhs_value)
        )

        if relation == "=":
            return self.square(self.subtract(lhs_expr, rhs_const))

        if relation == "<=":
            return self._inequality_expr(lhs_expr, rhs_const, constraint)

        if relation == ">=":
            return self._inequality_expr(rhs_const, lhs_expr, constraint)

        raise RuntimeError(f"Unsupported algebraic relation: {relation}") 
        
    def _resolve_expression(self, expr):

        if not isinstance(expr, dict):
            return expr

        # Normalize contract syntax → IR syntax
        expr = self._normalize_expression(expr)

        # Resolve derived metrics
        if expr.get("type") == "derived_metric":

            name = expr.get("name")

            return self.derived_metric_expressions.get(name, expr)

        return expr
    
    def _validate_index_projection(self, constraint):

        dv = self.semantic_root["decision_variables"]

        dv_indices = {
            idx.get("entity") or idx.get("structural_index")
            for idx in dv.get("indexing", [])
        }

        agg = constraint.get("aggregation", {})
        axes = agg.get("over", {})

        used = set(axes.get("entities", []) + axes.get("structural_indices", []))

        if not used.issubset(dv_indices):
            raise RuntimeError(
                f"Constraint '{constraint.get('id')}' uses indices {used} "
                f"outside decision variable index space {dv_indices}"
            )        
   
    # ==================================================
    # CARDINALITY
    # ==================================================
    def _compile_cardinality(self, constraint, weight):

        k = self._extract_rhs_value(constraint)

        variable = self.semantic_root["decision_variables"]["symbol"]

        axes = constraint.get("aggregation", {}).get("over")
        base_expr = self.aggregate(variable, axes)

        # --------------------------------------------------
        # Convert RHS into correct expression node
        # --------------------------------------------------

        if isinstance(k, str):
            rhs_expr = self.parameter(k)
        else:
            rhs_expr = self.constant(k)

        # Prefer algebraic schema relation
        relation = constraint.get("relation")

        # Backward compatibility with old schema
        quantifier = constraint.get("quantifier")

        # --------------------------------------------------
        # Equality constraint
        # --------------------------------------------------

        if relation == "=" or quantifier == "exact":

            expr = self.square(
                self.subtract(base_expr, rhs_expr)
            )

        # --------------------------------------------------
        # ≤ constraint
        # --------------------------------------------------

        elif relation == "<=" or quantifier == "at_most":

            expr = self._inequality_expr(base_expr, k)

        # --------------------------------------------------
        # ≥ constraint
        # --------------------------------------------------

        elif relation == ">=" or quantifier == "at_least":

            expr = self._inequality_expr(rhs_expr, base_expr)

        else:

            raise RuntimeError(
                f"Unsupported cardinality relation in constraint "
                f"{constraint.get('id')} "
                f"(relation={relation}, quantifier={quantifier})"
            )

        self._append_constraint(constraint["id"], weight, expr)

    def _extract_rhs_value(self, constraint):
        """
        Extract RHS scalar value from constraint.

        Supports multiple schema styles:
        1. Algebraic QEP schema:
            "rhs": { "value": 1 }

        2. Legacy compiler schema:
            "parameters": { "k": 1 }

        Returns
        -------
        numeric RHS value
        """

        if not isinstance(constraint, dict):
            raise RuntimeError(f"Invalid constraint structure: {constraint}")

        cid = constraint.get("id", "unknown")

        # ---- QEP algebraic schema ----
        rhs = constraint.get("rhs")
        if isinstance(rhs, dict) and "value" in rhs:

            value = rhs["value"]

            if rhs.get("source") == "parameter":
                self.parameter_references.add(value)
                return value

            return value  # allow parameter reference

        # ---- Legacy parameter schema ----
        params = constraint.get("parameters")
        if isinstance(params, dict) and "k" in params:
            return params["k"]

        # ---- Missing RHS ----
        raise RuntimeError(
            f"Constraint '{cid}' missing RHS value "
            "(expected rhs.value or parameters.k)"
        )

    # ==================================================
    # WEIGHTED SUM
    # ==================================================

    def _compile_weighted_sum(self, constraint, weight):

        field = constraint["field"]
        limit = constraint["parameters"]["limit"]

        variable = self.semantic_root["decision_variables"]["symbol"]

        base_expr = self.weighted_aggregate(variable, field)

        expr = self._inequality_expr(base_expr, limit)

        self._append_constraint(constraint["id"], weight, expr)

    # ==================================================
    # EXCLUSIVITY
    # ==================================================

    def _compile_exclusivity(self, constraint, weight):

        variable = self.semantic_root["decision_variables"]["symbol"]

        base_expr = self.aggregate(variable)

        expr = self._inequality_expr(base_expr, 1)

        self._append_constraint(constraint["id"], weight, expr)

    # ==================================================
    # INEQUALITY
    # ==================================================

    def _compile_inequality_le(self, constraint, weight):

        base_expr = constraint["lhs_expression_tree"]
        bound = constraint["bound"]

        expr = self._inequality_expr(base_expr, bound)

        self._append_constraint(constraint["id"], weight, expr)

    # --------------------------------------------------
    
   

    def _size_slack(self, upper_bound):

        if upper_bound <= 0:
            return 1

        return math.ceil(math.log2(upper_bound + 1))

    def _inequality_expr(self, left_expr, right_node, constraint=None):

        # ------------------------------------------------
        # Normalize expression so aggregation nodes exist
        # ------------------------------------------------
        left_expr = self._normalize_expression(left_expr)

        # ------------------------------------------------
        # Optimization: avoid slack for ≤1 cardinality
        # ------------------------------------------------
        if (
            isinstance(right_node, (int, float)) and right_node == 1
        ) or (
            isinstance(right_node, dict)
            and right_node.get("type") == "constant"
            and right_node.get("value") == 1
        ):
            return {
                "type": "pairwise_exclusion",
                "expression": left_expr
            }

        # ------------------------------------------------
        # Normalize RHS bound for slack sizing
        # ------------------------------------------------
        upper_bound = None

        if isinstance(right_node, (int, float)):
            upper_bound = right_node

        elif isinstance(right_node, dict):

            if right_node.get("type") == "constant":
                upper_bound = right_node["value"]

            elif right_node.get("type") == "parameter":
                # runtime parameter → slack auto-sized later
                upper_bound = None

        # ------------------------------------------------
        # Determine constraint scope
        # Prefer quantifier scope (compiler invariant)
        # ------------------------------------------------
        axes = {}

        q = constraint.get("quantifier") if constraint else None

        if q:
            axes = {
                "entities": q.get("entities", []),
                "structural_indices": q.get("structural_indices", [])
            }

        # ------------------------------------------------
        # Fallback: extract from aggregation expression
        # ------------------------------------------------
        if not axes:
            axes = self._extract_expression_scope(left_expr)

        # ------------------------------------------------
        # Final fallback: decision variable scope
        # ------------------------------------------------
        if not axes:

            dv = self.semantic_root["decision_variables"]

            axes = {
                "entities": [
                    idx.get("entity")
                    for idx in dv.get("indexing", [])
                    if idx.get("entity")
                ],
                "structural_indices": [
                    idx.get("structural_index")
                    for idx in dv.get("indexing", [])
                    if idx.get("structural_index")
                ]
            }

        axes = axes or {}

        # ------------------------------------------------
        # Declare indexed slack variable
        # ------------------------------------------------
        slack = self._declare_slack_variable(
            upper_bound=upper_bound,
            index_sets=axes
        )

        slack_expr = {
            "type": "slack_expansion",
            "slack_variable": slack,
            "encoding": {"type": "binary_weighted"}
        }

        # ------------------------------------------------
        # Hamiltonian
        # (LHS + slack − RHS)^2
        # ------------------------------------------------
        return self.square(
            self.subtract(
                self.add(left_expr, slack_expr),
                right_node
            )
        )       
        
        
    def _extract_expression_scope(self, expr):

        if not isinstance(expr, dict):
            return {}

        # aggregation defines scope
        if expr.get("type") in ["aggregation", "weighted_aggregation"]:
            return expr.get("over", {})

        # recursively search entire expression tree
        for value in expr.values():

            if isinstance(value, dict):
                scope = self._extract_expression_scope(value)
                if scope:
                    return scope

            if isinstance(value, list):
                for v in value:
                    scope = self._extract_expression_scope(v)
                    if scope:
                        return scope

        return {}

    def _compile_flow(self, constraint, weight):

        self.metadata["flow_constraints_present"] = True

        expr = self.square({
            "type": "flow_balance",
            "variable": self.semantic_root["decision_variables"]["symbol"]
        })

        self._append_constraint(constraint["id"], weight, expr)

    # ==================================================
    # TEMPORAL
    # ==================================================

    def _compile_temporal(self, constraint, weight):

        self.metadata["temporal_constraints_present"] = True
        big_m_param = "big_M"

        self.parameter_references.add(big_m_param)
        expr = self.square({
            "type": "time_propagation",
            "decision_variable": self.semantic_root["decision_variables"]["symbol"],
            "big_m_parameter": big_m_param
        })

        self._append_constraint(constraint["id"], weight, expr)

    # ==================================================
    # ROUTING
    # ==================================================

    def _compile_routing(self, constraint, weight):

        expr = self.square({
            "type": "connection_enforcement",
            "variable": self.semantic_root["decision_variables"]["symbol"]
        })

        self._append_constraint(constraint["id"], weight, expr)

    # ==================================================
    # PRECEDENCE
    # ==================================================

    def _compile_precedence(self, constraint, weight):

        self.metadata["precedence_constraints_present"] = True

        expr = self.square({
            "type": "precedence_chain",
            "variable": self.semantic_root["decision_variables"]["symbol"]
        })

        self._append_constraint(constraint["id"], weight, expr)

    # ==================================================
    # ASSIGNMENT
    # ==================================================

    def _compile_assignment(self, constraint, weight):

        expr = self.square({
            "relation": "one_to_many",
            "base_left": self.semantic_root["decision_variables"]["symbol"]
        })

        self._append_constraint(constraint["id"], weight, expr)

    # ==================================================
    # OBJECTIVE
    # ==================================================

    def _compile_objective(self, objective):

        bindings = self.semantic_root.get("objective_metric_bindings", {})

        if not bindings:
            return

        dv_symbol = self.semantic_root["decision_variables"]["symbol"]

        # --------------------------------------------------
        # Normalize objective input (dict or list)
        # --------------------------------------------------

        if isinstance(objective, list):
            objective_names = {o.get("name") for o in objective}
            goal = self.semantic_root.get("objective", {}).get("goal", "minimize")
        else:
            objective_names = (
                {objective.get("name")}
                if objective.get("name")
                else set(bindings.keys())
            )
            goal = objective.get("goal", "minimize")

        # --------------------------------------------------
        # Compile only objectives present in stage
        # --------------------------------------------------

        for metric_name, binding in bindings.items():

            if objective_names and metric_name not in objective_names:
                continue

            field = binding["field"]
            dataset_role = binding.get("dataset_role", "primary")
            normalize_required = binding.get("normalize", False)

            # --------------------------------------------------
            # Resolve dataset from entity bindings
            # --------------------------------------------------

            entity_binding = self.semantic_root.get("entity_bindings", {}).get(dataset_role)

            if not entity_binding:
                raise RuntimeError(
                    f"Objective metric binding references unknown dataset_role '{dataset_role}'"
                )

            dataset_name = entity_binding.get("source")

            dataset = self.datasets.get(dataset_name)

            if dataset is None:
                raise RuntimeError(
                    f"Dataset '{dataset_name}' required for objective metric '{metric_name}' not loaded."
                )

            # --------------------------------------------------
            # Extract metric values
            # --------------------------------------------------

            values = self._extract_metric_values(dataset, field)

            if not values:
                raise RuntimeError(
                    f"No values extracted for objective metric '{metric_name}'"
                )

            # --------------------------------------------------
            # Optional normalization
            # --------------------------------------------------

            values = self._normalize(values, normalize_required)

            # --------------------------------------------------
            # Convert maximize → minimize
            # --------------------------------------------------

            if goal == "maximize":
                values = [-v for v in values]

            # --------------------------------------------------
            # Objective scaling (prevents penalty dominance)
            #
            # In QUBO formulations, constraint penalties often
            # have magnitudes ~100–1000. If objective coefficients
            # are very small (e.g., returns 0.05–0.2), the solver
            # may ignore the objective entirely.
            #
            # To maintain numerical conditioning, we scale the
            # objective so its largest coefficient is around ~10.
            # This keeps penalties dominant while preserving
            # meaningful optimization gradients.
            # --------------------------------------------------

            max_abs = max(abs(v) for v in values)

            if max_abs > 0:

                target_scale = 10.0
                scale_factor = target_scale / max_abs

                values = [v * scale_factor for v in values]

                # record scaling metadata for debugging / audit
                self.metadata["objective_scaled"] = True
                self.metadata["objective_scale_factor"] = scale_factor

        # --------------------------------------------------
        # Emit objective terms
        # --------------------------------------------------

        for idx, coeff in enumerate(values):

            term = {
                "type": "linear",
                "coefficient": {
                    "type": "constant",
                    "value": coeff
                },
                "variable": dv_symbol,
                "index": [idx]
            }

            self.objective_terms.append(term)
            

    # ==================================================
    # PAIRWISE OBJECTIVE
    # ==================================================

    def _compile_pairwise_objective(self):

        interaction = self.semantic_root.get("interaction")

        if not interaction or not interaction.get("enabled"):
            return

        field = interaction.get("relationship_field")
        var = self.semantic_root["decision_variables"]["symbol"]

        self.objective_terms.append({
            "id": "pairwise_interaction",
            "type": "quadratic",
            "applies_to": {"variable": var},
            "interaction": {
                "enabled": True,
                "relationship_field": field,
                "variables": [var, var]
            }
        })

    # ==================================================
    # RELATIONSHIP GATING
    # ==================================================

    def _compile_relationship_gating(self, stage):

        gating = stage.get("relationship_gating")

        if not gating:
            return

        var = self.semantic_root["decision_variables"]["symbol"]
        field = gating.get("relationship_field")

        expr = self.square({
            "type": "relationship_gate",
            "variable": var,
            "relationship_field": field
        })

        self._append_constraint("relationship_gate", 1000, expr)

    # ==================================================
    # NORMALIZATION
    # ==================================================

    def _normalize(self, values, normalize_required):

        if not values:
            return values

        cfg = getattr(self, "numeric_scale_cfg", {})

        if not (cfg.get("enabled", False) and normalize_required):
            return values

        raw_min = min(values)
        raw_max = max(values)

        self.metadata["normalization_applied"] = True

        if raw_max == raw_min:
            return [0.0] * len(values)

        scale = raw_max - raw_min

        return [(v - raw_min) / scale for v in values]
        
    
    
    
    def _normalize_expression(self, expr):
        """
        Normalize expression nodes from contract/QEP format
        into canonical IR expression schema.
        """

        if not isinstance(expr, dict):
            return expr

        # --------------------------------------
        # Convert expression_type aggregation
        # --------------------------------------
        if expr.get("expression_type") == "aggregation":

            agg = expr.get("aggregation", {})

            return {
                "type": "aggregation",
                "variable": agg.get("variable"),
                "field": agg.get("field"),
                "dataset_role": agg.get("dataset_role"),
                "over": agg.get("over", {}),
                "interaction": agg.get("interaction", {"enabled": False})
            }

        # --------------------------------------
        # Recursively normalize children
        # --------------------------------------
        for k, v in expr.items():
            if isinstance(v, dict):
                expr[k] = self._normalize_expression(v)
            elif isinstance(v, list):
                expr[k] = [
                    self._normalize_expression(i) for i in v
                ]

        return expr

    # ==================================================
    # EXPRESSION HELPERS
    # ==================================================

    def constant(self, value):
        return {"type": "constant", "value": value}
        
    def parameter(self, name):
        return {
            "type": "parameter",
            "name": name
        }

    def aggregate(self, variable, axes=None):

        expr = {
            "type": "aggregation",
            "variable": variable
        }

        if axes:
            expr["over"] = axes

        return expr

    def weighted_aggregate(self, variable, field, axes=None):

        expr = {
            "type": "weighted_aggregation",
            "variable": variable,
            "field": field
        }

        if axes:
            expr["over"] = axes

        return expr
        
    def subtract(self, left, right):
        return {"type": "subtract", "left": left, "right": right}

    def add(self, left, right):
        return {"type": "add", "left": left, "right": right}

    def square(self, expr):
        return {"type": "square", "argument": expr}

    # ==================================================

    def _append_constraint(self, cid, weight, expr_tree):

        expr_tree = self._normalize_expression(expr_tree)

        self.constraints.append({
            "id": cid,
            "type": "quadratic_penalty",
            "penalty_weight": {"mode": "constant", "value": weight},
            "expression": {
                "form": "general_quadratic",
                "expression_tree": expr_tree
            }
        })
    
    # ==================================================
    # VARIABLES
    # ==================================================

    def _declare_variables(self):

        dv = self.semantic_root["decision_variables"]
        symbol = dv["symbol"]

        self.variables[symbol] = {
            "primitive": dv.get("type", "binary"),
            "structure": "indexed",
            "origin": "decision_variable",
            "index_sets": [
                {
                    "name": idx.get("entity") or idx.get("structural_index"),
                    "kind": "entity"
                }
                for idx in dv.get("indexing", [])
            ]
        }

        self.metadata["variable_count_estimate"] += 1
    # ==================================================

    def _extract_metric_values(self, dataset, field):

        values = []

        for row in dataset:

            if field not in row:
                raise RuntimeError(
                    f"Field '{field}' missing in dataset row during objective extraction."
                )

            value = row[field]

            try:
                values.append(float(value))
            except (TypeError, ValueError):
                raise RuntimeError(
                    f"Invalid numeric value '{value}' for objective field '{field}'."
                )

        return values

    # ==================================================
    # DERIVED METRICS
    # ==================================================

    def _expand_derived_metrics(self):

        derived = self.semantic_root.get("derived_metrics") or {}

        self.derived_metric_expressions = {}

        for name, definition in derived.items():

            self.derived_metric_expressions[name] = {
                "type": "derived_metric",
                "definition": definition
            }


    # ==================================================

    def _resolve_tier(self, cid):

        for tier, ids in self.constraint_tiers.items():
            if cid in ids:
                return tier

        return "T2_OPERATIONAL"

    # ==================================================
    # IR OUTPUT
    # ==================================================

    def _emit_ir(self, stage):

        return {
            "ir_type": "universal_qubo_problem_ir",
            "version": "5.1",
            "problem_id": stage.get("qubo_id"),
            "variables": copy.deepcopy(self.variables),
            "parameters": copy.deepcopy(self.parameters),
            "objective": {"sense": "minimize", "terms": copy.deepcopy(self.objective_terms)},
            "constraints": copy.deepcopy(self.constraints),
            "metadata": {

                "variable_count_estimate": self.metadata["variable_count_estimate"],
                "slack_variable_count": self.metadata["slack_variable_count"],
                "slack_total_bit_count": self.metadata["slack_total_bit_count"],
                "constraint_count": len(self.constraints),

                "flow_constraints_present": self.metadata["flow_constraints_present"],
                "temporal_constraints_present": self.metadata["temporal_constraints_present"],
                "precedence_constraints_present": self.metadata["precedence_constraints_present"],

                "normalization_applied": self.metadata["normalization_applied"],
                "structural_indices_resolved": self.metadata["structural_indices_resolved"],

                "coupling_density": "sparse",
                "scalability_class": "quadratic",
                "inequality_safe": True,

                "compile_timestamp": datetime.utcnow().isoformat()
            }
        }
    def _validate_parameter_consistency(self):

        declared = {p["name"] for p in self.parameters}

        missing = self.parameter_references - declared
        unused = declared - self.parameter_references

        if missing:
            raise RuntimeError(
                f"Parameters referenced but not declared in required_parameters: {missing}"
            )

        if unused:
            raise RuntimeError(
                f"Unused parameters declared in required_parameters: {unused}"
            )
    def _validate_ir(self, ir):
        """
        Validate generated Universal QUBO IR using the IR validator.
        """

        try:

            validator = UniversalIRValidator()

            validator.validate(ir)

        except IRValidationError as e:

            raise RuntimeError(
                f"Generated IR failed validation: {str(e)}"
            )

# ==================================================
# MAIN
# ==================================================

def main():

    resolved_request = load_json("resolved_optimization_problem_request.json")
    qep = load_json("qubo_execution_plan_problem.json")

    compiler = UniversalQuboCompiler(resolved_request)

    compiled = []

    for stage in qep.get("qubo_stages", []):
        compiled.append(compiler.compile(stage))

    with open("universal_qubo_ir_output.json", "w") as f:
        json.dump(compiled, f, indent=2)

    print("✅ Universal QUBO IR generated")

if __name__ == "__main__":
    main()
