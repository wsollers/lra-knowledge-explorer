# Reorder Processed Batches Status

Generated: 2026-06-17 23:04:26 -04:00

Scope: batches with at least one `resolution-*.json` file. The apply phase has not produced `progress.yaml`, `patches.yaml`, `suspicious.yaml`, or `focus-queue.yaml` in the processed batch folders at generation time.

## Summary

- Total manifest batches: 35
- Batches with semantic-pass resolutions: 3
- Graphs in manifest: 1784
- Graphs in processed batches: 249
- Resolution files present: 224
- Unresolved graphs within processed batches: 25
- Verdict totals: ok 168, reorder 0, change 56, other 0

## Processed Batch Table

| Batch | Volume | Chapter | Status | Graphs | Resolutions | Unresolved Graphs | OK | Reorder | Change | Other | Avg Confidence | Min Confidence | Last Resolution |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| batch-0033 | i | propositional-logic | partial | 133 | 108 | 25 | 97 | 0 | 11 | 0 | 0.66 | 0.50 | 2026-06-17 22:52:22 |
| batch-0034 | i | predicate-logic | complete | 93 | 93 | 0 | 58 | 0 | 35 | 0 | 0.67 | 0.50 | 2026-06-17 21:11:53 |
| batch-0035 | i | axiom-systems | complete | 23 | 23 | 0 | 13 | 0 | 10 | 0 | 0.66 | 0.50 | 2026-06-17 19:23:48 |

## Change Candidates

These are the resolution files whose verdict is `change`; they should be reviewed before any automated application step. The `Current Dependencies` column comes from the sibling `graph-*.json` file, while `Proposed Dependencies` comes from the `resolution-*.json` file.

### batch-0033 - volume i, propositional-logic

| Graph | Resolution | Term | Current Dependencies | Proposed Dependencies | Adds | Removes | Confidence |
|---|---|---|---|---|---|---|---:|
| 0033-0013 | `resolution-0013.json` | `def:counterexample-assignment-propositional-logic` | def:truth-assignment-propositional-logic, def:valid-argument-form-propositional-logic | def:argument-form-propositional-logic, def:satisfaction-propositional-formula, def:truth-assignment-propositional-logic, def:valid-argument-form-propositional-logic | def:argument-form-propositional-logic, def:satisfaction-propositional-formula | (none) | 0.55 |
| 0033-0054 | `resolution-0054.json` | `def:nand-connective-propositional-logic` | def:logical-connective, def:truth-assignment-propositional-logic | def:logical-connective, def:logical-equivalence-propositional-logic, def:truth-assignment-propositional-logic | def:logical-equivalence-propositional-logic | (none) | 0.60 |
| 0033-0057 | `resolution-0057.json` | `def:nor-connective-propositional-logic` | def:logical-connective, def:truth-assignment-propositional-logic | def:logical-connective, def:logical-equivalence-propositional-logic, def:truth-assignment-propositional-logic | def:logical-equivalence-propositional-logic | (none) | 0.60 |
| 0033-0070 | `resolution-0070.json` | `def:conjunctive-normal-form-propositional-logic` | (none) | def:clause-propositional-logic | def:clause-propositional-logic | (none) | 0.70 |
| 0033-0071 | `resolution-0071.json` | `def:elementary-disjunction-propositional-logic` | (none) | def:literal-propositional-logic | def:literal-propositional-logic | (none) | 0.65 |
| 0033-0072 | `resolution-0072.json` | `def:maxterm-propositional-logic` | (none) | def:elementary-disjunction-propositional-logic, def:literal-propositional-logic | def:elementary-disjunction-propositional-logic, def:literal-propositional-logic | (none) | 0.55 |
| 0033-0074 | `resolution-0074.json` | `def:disjunctive-normal-form-propositional-logic` | (none) | def:elementary-conjunction-propositional-logic | def:elementary-conjunction-propositional-logic | (none) | 0.70 |
| 0033-0075 | `resolution-0075.json` | `def:elementary-conjunction-propositional-logic` | (none) | def:literal-propositional-logic | def:literal-propositional-logic | (none) | 0.65 |
| 0033-0076 | `resolution-0076.json` | `def:minterm-propositional-logic` | (none) | def:elementary-conjunction-propositional-logic, def:literal-propositional-logic | def:elementary-conjunction-propositional-logic, def:literal-propositional-logic | (none) | 0.55 |
| 0033-0087 | `resolution-0087.json` | `def:negation-normal-form-propositional-logic` | def:literal-propositional-logic, def:logical-equivalence-propositional-logic, def:well-formed-formula | def:literal-propositional-logic, def:well-formed-formula | (none) | def:logical-equivalence-propositional-logic | 0.60 |
| 0033-0102 | `resolution-0102.json` | `def:truth-assignment-propositional-logic` | def:propositional-variable, def:truth-value-propositional-logic, def:well-formed-formula | def:propositional-variable, def:truth-value-propositional-logic | (none) | def:well-formed-formula | 0.65 |

### batch-0034 - volume i, predicate-logic

| Graph | Resolution | Term | Current Dependencies | Proposed Dependencies | Adds | Removes | Confidence |
|---|---|---|---|---|---|---|---:|
| 0034-0002 | `resolution-0002.json` | `ax:predicate-logic-universal-instantiation` | (none) | def:free-for, def:subst-notation | def:free-for, def:subst-notation | (none) | 0.55 |
| 0034-0008 | `resolution-0008.json` | `thm:eq-trans` | def:eq-elim, def:eq-refl | def:eq-elim | (none) | def:eq-refl | 0.60 |
| 0034-0013 | `resolution-0013.json` | `def:fol-completeness` | (none) | def:log-consequence | def:log-consequence | (none) | 0.60 |
| 0034-0015 | `resolution-0015.json` | `thm:fol-sound` | ax:predicate-logic-quantifier-distribution, ax:predicate-logic-universal-instantiation, def:fol-satisfaction, def:fol-soundness, def:log-consequence | ax:predicate-logic-quantifier-distribution, ax:predicate-logic-universal-instantiation, def:eg, def:ei, def:fol-satisfaction, def:fol-soundness, def:log-consequence, def:ug, def:ui | def:eg, def:ei, def:ug, def:ui | (none) | 0.60 |
| 0034-0017 | `resolution-0017.json` | `def:existential-q` | def:variable | def:variable, def:wff-pred | def:wff-pred | (none) | 0.80 |
| 0034-0018 | `resolution-0018.json` | `def:open-formula-quantifiers` | def:predicate, def:wff-pred | def:fv, def:predicate, def:wff-pred | def:fv | (none) | 0.80 |
| 0034-0020 | `resolution-0020.json` | `def:sentence-predicate-logic` | def:wff-pred | def:fv, def:wff-pred | def:fv | (none) | 0.80 |
| 0034-0021 | `resolution-0021.json` | `def:universal-q` | def:variable | def:variable, def:wff-pred | def:wff-pred | (none) | 0.80 |
| 0034-0026 | `resolution-0026.json` | `thm:dependent-witness-not-uniform` | thm:uniform-witness-implies-dependent-witness | def:log-consequence, thm:uniform-witness-implies-dependent-witness | def:log-consequence | (none) | 0.60 |
| 0034-0027 | `resolution-0027.json` | `thm:existential-not-universal` | thm:universal-implies-existential | def:log-consequence, thm:universal-implies-existential | def:log-consequence | (none) | 0.60 |
| 0034-0030 | `resolution-0030.json` | `def:matrix-prenex` | def:wff-pred | def:quantifier-prefix, def:wff-pred | def:quantifier-prefix | (none) | 0.65 |
| 0034-0033 | `resolution-0033.json` | `def:quantifier-prefix` | def:existential-q, def:universal-q | def:existential-q, def:universal-q, def:variable | def:variable | (none) | 0.75 |
| 0034-0035 | `resolution-0035.json` | `thm:invalid-quantifier-distribution` | thm:qdist | def:log-equiv, thm:qdist | def:log-equiv | (none) | 0.60 |
| 0034-0036 | `resolution-0036.json` | `thm:mixed-quantifiers-do-not-commute` | thm:qcomm | def:log-equiv, thm:qcomm | def:log-equiv | (none) | 0.60 |
| 0034-0037 | `resolution-0037.json` | `thm:qcomm` | def:existential-q, def:universal-q | def:existential-q, def:log-equiv, def:universal-q | def:log-equiv | (none) | 0.75 |
| 0034-0040 | `resolution-0040.json` | `thm:quantifier-double-negation` | thm:qneg | def:log-equiv, thm:qneg | def:log-equiv | (none) | 0.60 |
| 0034-0041 | `resolution-0041.json` | `thm:rename` | def:free-for, def:subst-notation | def:free-for, def:log-equiv, def:subst-notation | def:log-equiv | (none) | 0.65 |
| 0034-0042 | `resolution-0042.json` | `thm:vacuous` | def:quantifier-scope | def:bound-free, def:log-equiv, def:quantifier-scope | def:bound-free, def:log-equiv | (none) | 0.60 |
| 0034-0043 | `resolution-0043.json` | `def:log-consequence` | def:model-theory-set, def:theory | def:model, def:model-theory-set, def:theory | def:model | (none) | 0.65 |
| 0034-0047 | `resolution-0047.json` | `def:theory` | def:truth-structure | def:sentence-predicate-logic | def:sentence-predicate-logic | def:truth-structure | 0.75 |
| 0034-0049 | `resolution-0049.json` | `def:predicate` | def:predicate-symbol, def:wff-pred | def:fv, def:predicate-symbol, def:wff-pred | def:fv | (none) | 0.70 |
| 0034-0051 | `resolution-0051.json` | `lem:subst-terms` | def:free-for, def:subst-notation, def:term-interp | def:subst-notation, def:term-interp | (none) | def:free-for | 0.60 |
| 0034-0061 | `resolution-0061.json` | `def:formula-depth` | (none) | def:atomic-formula, def:wff-pred | def:atomic-formula, def:wff-pred | (none) | 0.60 |
| 0034-0063 | `resolution-0063.json` | `def:constant-symbol` | def:variable | def:arity, def:variable | def:arity | (none) | 0.60 |
| 0034-0064 | `resolution-0064.json` | `def:formula` | def:language | def:atomic-formula, def:language | def:atomic-formula | (none) | 0.65 |
| 0034-0065 | `resolution-0065.json` | `def:function-symbol` | def:constant-symbol | def:arity, def:constant-symbol | def:arity | (none) | 0.60 |
| 0034-0067 | `resolution-0067.json` | `def:predicate-symbol` | def:function-symbol | def:arity, def:function-symbol | def:arity | (none) | 0.60 |
| 0034-0068 | `resolution-0068.json` | `def:term` | def:language | def:constant-symbol, def:function-symbol, def:language, def:variable | def:constant-symbol, def:function-symbol, def:variable | (none) | 0.70 |
| 0034-0070 | `resolution-0070.json` | `def:wff-pred` | def:formula | def:atomic-formula, def:formula, def:variable | def:atomic-formula, def:variable | (none) | 0.65 |
| 0034-0071 | `resolution-0071.json` | `def:alpha-equiv` | (none) | def:bound-free, def:log-equiv, def:subst-notation | def:bound-free, def:log-equiv, def:subst-notation | (none) | 0.60 |
| 0034-0073 | `resolution-0073.json` | `def:free-for` | (none) | def:bound-free, def:scope, def:subst-notation, def:term | def:bound-free, def:scope, def:subst-notation, def:term | (none) | 0.60 |
| 0034-0076 | `resolution-0076.json` | `def:sentence` | (none) | def:fv, def:wff-pred | def:fv, def:wff-pred | (none) | 0.70 |
| 0034-0077 | `resolution-0077.json` | `def:subst-notation` | (none) | def:bound-free, def:term, def:variable | def:bound-free, def:term, def:variable | (none) | 0.60 |
| 0034-0081 | `resolution-0081.json` | `def:translation-key-predicate-logic` | def:constant-symbol, def:predicate-symbol | def:constant-symbol, def:predicate-symbol, def:relation-symbol | def:relation-symbol | (none) | 0.65 |
| 0034-0082 | `resolution-0082.json` | `def:translation-predicate-relation-symbol` | def:atomic-formula, def:predicate-symbol | def:atomic-formula, def:predicate-symbol, def:relation-symbol | def:relation-symbol | (none) | 0.60 |

### batch-0035 - volume i, axiom-systems

| Graph | Resolution | Term | Current Dependencies | Proposed Dependencies | Adds | Removes | Confidence |
|---|---|---|---|---|---|---|---:|
| 0035-0001 | `resolution-0001.json` | `def:assumption` | def:axiom | (none) | (none) | def:axiom | 0.78 |
| 0035-0002 | `resolution-0002.json` | `def:axiom` | def:language | def:theory | def:theory | def:language | 0.60 |
| 0035-0007 | `resolution-0007.json` | `def:axiom-systems-model-existence-criterion` | def:axiom-systems-model | def:axiom-system, def:axiom-systems-model | def:axiom-system | (none) | 0.62 |
| 0035-0009 | `resolution-0009.json` | `def:axiom-systems-countermodel` | def:axiom-systems-model, def:axiom-systems-satisfaction | def:axiom-systems-consequence, def:axiom-systems-satisfaction, def:axiom-systems-structure | def:axiom-systems-consequence, def:axiom-systems-structure | def:axiom-systems-model | 0.55 |
| 0035-0011 | `resolution-0011.json` | `def:axiom-systems-model` | def:axiom-systems-structure, def:axiom-systems-theory | def:axiom-systems-satisfaction, def:axiom-systems-structure, def:axiom-systems-theory | def:axiom-systems-satisfaction | (none) | 0.72 |
| 0035-0012 | `resolution-0012.json` | `def:axiom-systems-satisfaction` | def:axiom-systems-structure | def:axiom-systems-structure, def:term, def:wff-pred | def:term, def:wff-pred | (none) | 0.60 |
| 0035-0015 | `resolution-0015.json` | `def:language` | def:signature | def:signature, def:term, def:wff-pred | def:term, def:wff-pred | (none) | 0.58 |
| 0035-0020 | `resolution-0020.json` | `def:axiom-systems-consequence` | def:axiom-systems-theory | def:axiom-systems-model | def:axiom-systems-model | def:axiom-systems-theory | 0.60 |
| 0035-0022 | `resolution-0022.json` | `def:axiom-systems-theory` | def:axiom-system, def:language | def:axiom-system, def:deductive-closure, def:language, def:sentence | def:deductive-closure, def:sentence | (none) | 0.55 |
| 0035-0023 | `resolution-0023.json` | `def:deductive-closure` | def:axiom-system | def:sentence | def:sentence | def:axiom-system | 0.50 |

## Unprocessed Batches

The following batches currently have graph files but no `resolution-*.json` files, so they are outside this processed-batch report:

| Batch | Volume | Chapter | Graphs |
|---|---:|---|---:|
| batch-0001 | viii | model-theory | 4 |
| batch-0002 | viii | lambda-calculus | 1 |
| batch-0003 | viii | algebras-of-sets | 6 |
| batch-0004 | viii | numerical-analysis | 19 |
| batch-0005 | viii | ordinary-differential-equations | 16 |
| batch-0006 | viii | computational-geometry | 10 |
| batch-0007 | vii | euclidean-geometry | 36 |
| batch-0008 | vii | analytical-geometry | 8 |
| batch-0009 | vi | linear-algebra | 23 |
| batch-0010 | vi | lattice-order | 29 |
| batch-0011 | vi | algebraic-structures | 102 |
| batch-0012 | vi | algebraic-geometry | 14 |
| batch-0013 | iv | foundations | 1 |
| batch-0014 | iii | sequences | 149 |
| batch-0015 | iii | real-analysis | 31 |
| batch-0016 | iii | functions | 69 |
| batch-0017 | iii | elementary-functions | 21 |
| batch-0018 | iii | differentiation | 56 |
| batch-0019 | iii | continuity | 62 |
| batch-0020 | iii | bounding | 43 |
| batch-0021 | ii | whole-numbers | 43 |
| batch-0022 | ii | structure-of-real-line | 25 |
| batch-0023 | ii | reals | 71 |
| batch-0024 | ii | rationals | 153 |
| batch-0025 | ii | peano-systems | 43 |
| batch-0026 | ii | number-lines | 6 |
| batch-0027 | ii | natural-numbers | 56 |
| batch-0028 | ii | integers | 122 |
| batch-0029 | ii | identity-equality-equivalence | 41 |
| batch-0030 | ii | embedding-number-systems | 14 |
| batch-0031 | ii | arithmetic-operations-relations | 118 |
| batch-0032 | i | sets-relations-functions | 143 |
