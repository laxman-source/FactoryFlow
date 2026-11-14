# How to continue FactoryFlow using Codex in VS Code

After you have successfully run the dashboard and tests, open Codex in the **same FactoryFlow folder** and paste this:

> You are my senior Python developer and manufacturing supply planner mentor. This is my standalone FactoryFlow Phase 1 starter project, using fictional factory data. First inspect every file. Do not rewrite the app unnecessarily. Run the tests and check whether all assumptions match the README. Explain any failures before changing code. Next, suggest THREE small improvements that would help a supply planner, ordered by business value and complexity. Choose only ONE improvement for Phase 2, then show your planned file changes and new test cases before implementing it. Never claim this is a full ERP or complete MRP system. Explain each technical term in simple English. Never use confidential or live company data.

## Phase 2 ideas (not implemented yet)

1. Support multiple demand dates (time-phased MRP).
2. Allow user edits to the fictional BOM and inventory in a safe local sandbox.
3. Export suggested purchases to a downloadable CSV, clearly labeled **simulation only**.
4. Add receipt delays and supplier reliability scenarios.
5. Introduce a simple Engineering Change Notice (ECN) showing BOM changes.

## Test questions for yourself

- What does BOM quantity per unit mean?
- Why can one component be needed by two finished products?
- What is the difference between gross requirement and net shortage?
- Why is an incoming purchase receipt not always usable in time?
- Why doesn't having enough materials guarantee the factory can produce on time?
