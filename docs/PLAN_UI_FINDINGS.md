# Plan UI in VS Code: findings and checks

## Findings

- VS Code has a built-in Plan flow (`/plan` or the **Plan** mode picker). In a **Copilot** session it shows a **Review Plan** card with **Open Full Plan**. In a **Local** session the plan is stored at `/memories/session/plan.md` and shows **Start Implementation** and **Open in Editor**.
- The VS Code docs describe no setting that renders arbitrary `plan_items` JSON as a table. Opening a JSON file from a handoff only opens a text file.
- The repo has two copies of the agent: `Plan.agent.md` (root) and `.github/agents/Plan.agent.md`. Only the `.github/agents` one is in a documented location.
- The custom agent is named "Plan", so it may shadow the built-in Plan agent. Its handoff prompts claim a Plan Table preview will appear above the chatbox, which the platform does not do.
- `/plan-table` in `backend/app/dashboard.py` serves sample data from `docs/plan_items_examples.json`, not real plans.

## Steps

1. Identify the work computer's UI: Review Plan card or a table? Record Session Target (Copilot or Local), VS Code version (Stable or Insiders), installed extensions, and any org-managed agents or settings.
2. Test the built-in flow here: run `/plan <task>` in a fresh Copilot-targeted chat, then a Local one, and note what appears.
3. Decide which Plan agent wins. To use the built-in UI, remove or rename the custom Plan agent. Keep only the `.github/agents` copy and delete the root duplicate.
4. If a real table is wanted, build it as a small extension (webview or custom editor for `plan_items`) or use an existing JSON-table viewer extension. An agent prompt cannot create the UI.
5. If keeping the local web page, point `/api/plan_items` at `plan_table_last.json` instead of the sample file.
6. Clean up the handoffs: remove claims that opening JSON triggers a UI.

## Verification

- A fresh `/plan` shows the expected card or table on both machines.
- The agent picker lists exactly one Plan agent.
- `/plan-table` shows current plan data.

## Open questions

- What exactly appears on the work machine, and which extension or tool produces it?
- Should this project use the built-in Review Plan card or a table?

## plan_items

{"plan_items":[{"id":"identify-work-ui","title":"Identify work computer Plan UI","description":"Record Session Target, VS Code version, extensions and whether it is the Review Plan card or a table.","status":"pending","owner":null,"due_date":null,"priority":"high","tags":["research","vscode"]},{"id":"test-builtin-plan","title":"Test built-in /plan flow","description":"Run /plan in Copilot and Local sessions and see which shows the Review Plan card.","status":"pending","owner":null,"due_date":null,"priority":"high","tags":["test","copilot"]},{"id":"resolve-agent-conflict","title":"Resolve duplicate or shadowing Plan agent","description":"Keep only .github/agents/Plan.agent.md, delete the root copy, and decide whether to keep a custom Plan agent over the built-in one.","status":"pending","owner":null,"due_date":null,"priority":"medium","tags":["config","agent"]},{"id":"build-table-ui","title":"Provide a real Plan Table renderer if needed","description":"Build a small extension or webview, or use a JSON table viewer, since agent prompts cannot create the UI.","status":"pending","owner":null,"due_date":null,"priority":"medium","tags":["ui","extension"]},{"id":"fix-local-preview","title":"Point /plan-table at real plan data","description":"Change /api/plan_items in dashboard.py to serve plan_table_last.json instead of sample data.","status":"pending","owner":null,"due_date":null,"priority":"low","tags":["backend","dashboard"]},{"id":"clean-handoffs","title":"Clean up handoff prompts","description":"Remove claims that opening JSON triggers a UI.","status":"pending","owner":null,"due_date":null,"priority":"low","tags":["agent","cleanup"]}]}
