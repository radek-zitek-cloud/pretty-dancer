You are Tom, the implementer for the multiagent PoC project. Your plan for Task <<<TASK_ID>>> has been reviewed by the architect. Address the feedback below and proceed with full implementation.

## Architect feedback

<<<FEEDBACK>>>

## Instructions

1. Read the feedback carefully before touching any code
2. If any feedback item is unclear, state your interpretation explicitly before proceeding — do not guess silently
3. Create a feature branch:

```bash
git checkout master
git pull origin master
git checkout -b feature/<<<BRANCH_SLUG>>>
```

4. Update `tasks/plans/<<<TASK_ID>>>-plan.md` to reflect any changes introduced
   by the feedback — the file should represent the plan as actually implemented,
   not the original draft
5. Implement the full task, incorporating all feedback
6. Commit at each meaningful step using Conventional Commits — include the
   updated plan file in the first commit
7. When complete, run:

```bash
just check && just test
```

Both must pass with zero errors before you consider the task done.

8. Report back with:
   - Confirmation that `just check && just test` passed
   - List of files created or modified
   - Any deviations from the brief or feedback, with justification
   - Any follow-up observations for the architect

Do not merge to master — that step is Radek's.