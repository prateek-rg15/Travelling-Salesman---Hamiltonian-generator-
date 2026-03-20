# Optimization Pipeline – Overview and Hamiltonian Engine Guide

## 1. Overview
This repository implements a modular optimization pipeline designed to transform a high-level optimization problem definition into a Hamiltonian representation suitable for QUBO/Ising-based quantum or classical optimization solvers.

The pipeline separates problem specification, compilation, and Hamiltonian generation to ensure:
- Clear modular architecture
- Reusable components
- Domain-independent optimization processing

The system supports multiple optimization problems (e.g., Travel Sequence Optimization, Portfolio Optimization) while using the same core pipeline.

---

## 2. Optimization Pipeline Architecture
Problem Definition
│
▼
Resolved Optimization Request
│
▼
QUBO Execution Plan (QEP)
│
▼
Hamiltonian Engine
│
▼
QUBO Problem IR
│
▼
Hamiltonian Expression JSON
│
▼
(QUBO Matrix / Solver / Quantum Execution – future stages)
### Stage Descriptions

1. **Problem Definition**  
A structured optimization request describing decision variables, constraints, datasets, and objectives.

2. **Resolved Optimization Request**  
The validated and fully expanded version of the optimization request.

3. **QUBO Execution Plan (QEP)**  
A staged plan defining how the optimization problem is compiled into QUBO form.

4. **Hamiltonian Engine**  
Transforms the QEP into a QUBO Intermediate Representation (IR).

5. **QUBO IR**  
A structured representation of the Hamiltonian problem.

6. **Hamiltonian Expression Generation**  
Human-readable Hamiltonian expressions derived from the IR.

---

## 3. Where the Hamiltonian Engine Fits


Optimization Request
│
▼
QUBO Execution Plan
│
▼
Hamiltonian Engine
│
├── QUBO Compiler
├── Dataset Loader
└── IR Generator
│
▼
QUBO Problem IR


### Responsibilities of the Hamiltonian Engine
- Loads problem datasets
- Processes the QUBO Execution Plan
- Compiles into QUBO IR
- Generates Hamiltonian IR
- Optionally generates Hamiltonian JSON

### Design Principles
- NO domain logic
- NO solver logic
- NO AI / GenAI logic

---

## 4. Directory Structure


Hamiltonian_Engine/
├── Travel_Sequence_Optimization/
│ ├── cities.csv
│ ├── travel_times.csv
│ ├── parameters.csv
│ ├── qubo_execution_plan_problem.json
│ └── resolved_optimization_problem_request.json
│
├── Portfolio_Optimization/
│ ├── assets.csv
│ ├── returns.csv
│ ├── parameters.csv
│ ├── qubo_execution_plan_problem.json
│ └── resolved_optimization_problem_request.json
│
├── Result/
│ └── <USER_ID>/
│ ├── qubo_problem_ir.json
│ └── hamiltonian_expression.json
│
├── pipeline_orchestrator.py
└── hamiltonian_from_ir.py


---

## 5. Running the Pipeline

### Step 1 — Start the Pipeline
```bash
python pipeline_orchestrator.py
Step 2 — Enter User ID
Enter 4-digit USER ID: 1001

This creates:

Result/1001/
Step 3 — Select Optimization Problem
1 → Travel Sequence Optimization  
2 → Portfolio Optimization  

Example:

Enter choice (1 or 2): 1
Step 4 — QUBO IR Generation

The pipeline will:

Load the problem datasets

Compile the QUBO Execution Plan

Generate the QUBO Problem IR

Output:

Result/<USER_ID>/qubo_problem_ir.json
Step 5 — Optional Hamiltonian Generation
Generate complete Hamiltonian JSON file? (Y/N)

If Y, output:

Result/<USER_ID>/hamiltonian_expression.json
6. Example Output
Result/1001/
├── qubo_problem_ir.json
└── hamiltonian_expression.json
7. Future Extensions

QUBO Matrix generation

Solver integration (classical / quantum)

QAOA or annealing execution

Solution decoding

Result analytics
