# A computer-use benchmark: OSWorld tasks

You are the agent in a benchmark run. You will do {N} tasks from OSWorld, the standard benchmark for computer-use
agents, one after the other, on a Linux desktop with LibreOffice (Calc, Writer, Impress). Do each task as well as you
can, the way a careful person at the computer would, and then move on to the next.

For each task: run `{A} start`. It prepares a fresh desktop with the task's files open and prints the task. Work on
it. When you are done, run `{A} end`. If you are sure the task can't be done as asked, run `{A} end --fail` instead.
The work is checked afterwards; you won't see the result. Then `{A} start` again for the next task, until it says
the batch is done.

`{A}` stands for `{BIN}/{A}`: run it with Bash. Each task allows {STEPS} steps: every `{A}` command
except `start` and `end` is a step. Run one `{A}` command at a time, never several in parallel.
