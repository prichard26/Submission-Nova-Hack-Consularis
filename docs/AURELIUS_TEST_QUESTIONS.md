# Test Questions for Aurelius

Use this list to check that the Aurelius agent behaves correctly: proposes plans for edits, answers with text only for analysis, asks for clarification when ambiguous, and executes plans when the user confirms.

---

## Your Examples (keep as-is)

- **In Selection, Acquisition, and Reception:** "Add a step of signing the shipment paper"
- **In Prescription:** "Can you add a step in between prescribe medication and verify prescription, that is print the prescription"
- **On the main map:** "Add the step Fill paperwork in care unit"

---

## Add Step (by process / phase name)

- In **Prescription:** "Add a step: Pharmacist reviews prescription, 2 minutes"
- In **Distribution:** "Add a step called Notify ward before delivery"
- In **Dispensing and Preparation:** "Add a step to double-check dosage"
- In **Storage and Storage Management:** "Add a step for temperature logging"
- In **Administration:** "Add a step: Record administration in patient chart"
- In **Monitoring and Waste Management:** "Add a step to document waste disposal"

---

## Add Step Between Two Steps (ordering)

- In Prescription: "Add a step between Verify Prescription and the next step: Get patient consent"
- In S2: "Insert a step between Receive order and Acquire medication: Validate supplier"
- "In Prescription, add 'Print prescription' between Prescribe medication and Verify prescription" (variant of your example)

---

## Add Step on Main / Global Map

- "On the main map, add a step: Initial triage"
- "Add a step at the beginning of the main process: Register patient"
- "Add Fill paperwork in care unit on the global map" (variant of your example)

---

## Rename / Update Metadata (no structure change)

- "Rename the step Verify Prescription to Check prescription validity"
- "Set the duration of Prescribe medication to 10 minutes"
- "Change the actor for Dispensing to Senior pharmacist"
- "Add a risk to the Storage step: temperature excursion"
- "In Prescription, set the SLA for Verify Prescription to 15 minutes"

---

## Add Decision or Branch

- "In Prescription, add a decision after Verify prescription: Prescription valid? If yes continue, if no add a step Reject and notify physician"
- "Add a decision in Distribution: Delivery urgent? with two outcomes"
- "In S1, add a decision 'Approved?' after the approval step, with one path to end and one to a new step Escalate"

---

## Add Subprocess / Phase on Main Map

- "Add a new phase between Distribution and Dispensing called Quality check, with two steps: Inspect batch and Log result"
- "On the main map, add a subprocess Compliance check between S6 and S7"
- "Insert a new subprocess between Selection and Storage named Supplier validation"

---

## Remove / Delete

- "Remove the step Print prescription from Prescription"
- "Delete the link between P1.2 and P1.3"
- "Remove the Compliance check subprocess from the main map" (if it exists)

---

## Analysis and Questions (no plan, text only)

- "What does the Prescription process do?"
- "Where are the bottlenecks in this process?"
- "Which steps have the highest error rate?"
- "Who is responsible for Dispensing?"
- "What is the automation potential of Verify prescription?"
- "Summarize the main map in one paragraph"
- "Which steps take more than 5 minutes?"

---

## Ambiguity (should ask for clarification)

- "Add a verification step" (multiple verification steps may exist)
- "Set the duration to 5 minutes" (no step specified)
- "Rename the storage step" (e.g. several steps in Storage)
- "Add a step after the first step" (depends which process)

---

## Edit After Analysis (propose_plan only when user asks to change)

- First ask: "Where are my bottlenecks?" → expect analysis only, no plan.
- Then: "Add a quality check after the bottleneck step" → expect a plan.

---

## Wrong Context / Impossible (should explain or reject)

- "Add an edge from Prescribe medication (in S1) to Receive order (in S2)" (cross-page edge; should explain or refuse)
- "Delete the start node of Prescription" (protected node)
- "Add a step between the global start and S1" (depends how you want global map to behave)

---

## Apply Plan Flow

- Propose any change, then reply with: "Apply", "Yes", "Apply plan", "Confirm" → should execute the stored plan and return a short summary.

---

You can run these in the UI (or via the chat API) and tick off: correct propose_plan for edits, text-only for analysis, clarification when ambiguous, and correct Apply behavior.
