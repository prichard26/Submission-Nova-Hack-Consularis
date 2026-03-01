# Pharmacy circuit BPMN – review and connection issues

## What works well

- **Phases (lanes)** match the medication circuit: Prescription → Selection/Acquisition → Storage → Distribution → Dispensing → Administration → Monitoring/Waste.
- **Tasks** have clear names, actors, and risks.
- **Main forward path** is readable: P1.1→P1.2→P1.3→P2.1, then P2.2→P2.3→P2.4→P3.1→P3.3, and P4.1→P4.2→P4.3→P6.1→P6.2→P6.3→P7.1.
- **Conditional branches** (in stock / out of stock, inpatient / outpatient, reorder / ward order / expired) are modeled.

## Issues that make it feel “weirdly connected”

### 1. **P3.2 (Monitor Storage Conditions) is disconnected**

- **Issue:** No incoming or outgoing sequence flow. It looks like an orphan.
- **Reality:** Monitoring is ongoing and feeds into the same “storage” phase.
- **Fix:** Add at least one flow so it’s part of the graph, e.g.:
  - **P3.1 → P3.2** (“Stored, monitor conditions”) and optionally **P3.2 → P3.3** (“Conditions OK, update inventory”), or
  - **P3.2 → P7.2** or **P7.3** when “Temperature excursion” / “Alert” (if you want to model exceptions).

### 2. **Outpatient path ends at P5.3 (Patient Counseling)**

- **Issue:** The only outgoing edge from P5.2 is “Outpatient” → P5.3. From P5.3 there is **no outgoing flow**.
- **Reality:** After counseling, the patient goes home; you may still want to represent “monitoring” (e.g. follow-up) or at least an explicit end.
- **Fix:** Add one outgoing flow from P5.3, e.g.:
  - **P5.3 → P7.1** (“Monitor patient response” for outpatient follow-up), or
  - **P5.3 → [end]** if you introduce an end event.

### 3. **“In stock” path skips Storage (P3)**

- **Issue:** P2.1 (Select Medication) has “In stock” → **P5.1** (Compound/Prepare). So the flow jumps from Selection directly to Dispensing and **never touches Storage (P3)**.
- **Reality:** Even when the item is in stock at selection, it usually comes from storage and/or is put back into storage tracking. The diagram doesn’t show that.
- **Fix (conceptual):** Either:
  - Add a flow **P3.3 → P2.1** (“Stock available for selection”) so “in stock” at P2.1 is clearly fed by inventory, and optionally **P2.1 → P3.1** or P3.3 when the pick is recorded; or
  - Keep the shortcut but add a label like “In stock (already in picking area)” and accept that storage is implicit for that path.

### 4. **Inpatient path: P5.2 → P4.1 (Dispensing before Distribution)**

- **Issue:** For “Inpatient”, the flow goes **P5.2 (Final Verification) → P4.1 (Prepare Distribution)**. So Dispensing (P5) appears **before** Distribution (P4) in the flow, while on the diagram P4 is drawn before P5. That can look backwards.
- **Reality:** For inpatients, pharmacy often prepares and verifies the medication, then sends it to distribution (carts/ADC). So the logic is correct; the “weird” part is the **visual order** of lanes vs. flow direction.
- **Fix:** No change needed if the process is correct; optionally add a short label on the flow (e.g. “Verified medication sent to distribution”) so readers see it’s intentional. If you want the diagram to feel less backwards, you could reorder lanes (e.g. Dispensing before Distribution) but that may conflict with standard “order of phases” in your docs.

### 5. **P3.3 (Inventory Management) as a single hub**

- **Issue:** P3.3 has **three** conditional outgoing flows (to P2.2, P4.1, P7.2). It’s correct but dense; the diagram can look “all over the place” from one box.
- **Reality:** Inventory does trigger reorders, ward picks, and expiry handling. The logic is fine.
- **Fix:** Optional – add a short description in the task or on the flows so each branch is clearly “Reorder”, “Ward order”, “Expired”. No structural change required.

### 6. **No explicit link from Storage to Dispensing**

- **Issue:** The only way to reach P5.1 is **P2.1 → P5.1 (In stock)**. There is no flow from P3 (Storage) or P3.3 to P5.1. So “stock for dispensing” seems to appear only at P2.1.
- **Reality:** In practice, dispensing uses stock that is stored (P3) and tracked (P3.3). The model implies that “selection” (P2.1) is the decision point and that “in stock” means no need to go through P2.2–P2.4–P3.
- **Fix:** For clarity, add one of:
  - **P3.3 → P5.1** with condition “Dispensing order, medication in stock”, or
  - **P3.3 → P2.1** (“Stock available for selection”) so the in-stock path is clearly fed by inventory (and P2.1 still branches to P5.1 when in stock).

---

## Summary table

| Issue | Severity | Suggested change |
|-------|----------|------------------|
| P3.2 has no flows | High | Add P3.1→P3.2 and e.g. P3.2→P3.3 (or P3.2→P7.x for alerts). |
| P5.3 has no outgoing flow | High | Add P5.3→P7.1 or P5.3→end. |
| In-stock path skips P3 | Medium | Add P3.3→P2.1 and/or P3.3→P5.1; or document the shortcut. |
| P5.2→P4.1 looks “backwards” | Low | Add clearer labels; optionally reorder lanes. |
| P3.3 three-way split | Low | Clarify with labels/descriptions. |

---

## Conclusion

The BPMN is **structurally valid** and the high-level phases and branches match the medication circuit. The “weirdly connected” feeling comes mainly from:

1. **One task with no flows** (P3.2).
2. **One path that stops** (outpatient at P5.3).
3. **In-stock path** that skips Storage and has no explicit link from inventory to dispensing.
4. **Visual order** of lanes vs. flow direction (Dispensing before Distribution for inpatients).

Applying the high- and medium-severity fixes above will make the diagram clearer and more consistent with how the process is usually described.
