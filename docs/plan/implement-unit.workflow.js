// Claude Code Workflow script: implement one Minion unit from docs/plan/units/<unit>.md.
// Launch it once per unit (all at the same time for maximum parallelism), e.g. args: {"unit": "hub"}.
export const meta = {
  name: 'minion-impl-unit',
  description: 'Implement one Minion unit from its spec file (parallel implementation)',
  phases: [{ title: 'Implement' }],
}

const UNITS = 'docs/plan/units'
const REPORT = {
  type: 'object',
  properties: {
    files: { type: 'array', items: { type: 'string' } },
    tests_command: { type: 'string' },
    tests_passed: { type: 'boolean' },
    test_summary: { type: 'string' },
    foundation_changes_needed: { type: 'array', items: { type: 'string' } },
    new_dependencies: { type: 'array', items: { type: 'string' } },
    contract_deviations: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['files', 'tests_passed', 'test_summary', 'foundation_changes_needed', 'new_dependencies', 'contract_deviations', 'notes'],
}

phase('Implement')
const unit = args.unit
const report = await agent(
  `Read ${UNITS}/COMMON.md (rules that apply to you) and then your unit spec ${UNITS}/${unit}.md, ` +
  `then implement the unit completely in this repository, test it until it passes, and return the report. ` +
  `Work carefully and completely - this is production code for a public open-source project.`,
  { label: `impl:${unit}`, phase: 'Implement', schema: REPORT },
)
return { unit, report }
