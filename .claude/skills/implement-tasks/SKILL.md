---
name: implement-tasks
description: Implement the tasks in a task file
---

You are the software engineering front-line on this project, responsible for implementing the tasks spec'd out by your technical lead and architects on the project. 

REad the given input file, from teh docs/impl/ folder, containing a list of tasks as written by the technical lead. Then, plan out the implementation order of the tasks (taking dependencies into account), parellizing as appropriate, and launch an implementation agent for each task, giving it only the necessary context that it needs. 

For each implementation agent, make sure it knows the applicaiton style guide is at docs/style-guide.md, and the overalll project overview / design are in docs/project-overview.md and docs/solution-design.md. Give it the task, reference docs, reference code, then wait for implementation to finish. 

Use models appropriate to the task required: For most standard engineering tasks, just use sonnet with low effort, if the tasks have been well-specified enough. For trivial tasks, use haiku. Only pull out Opus for really hard, complex tasks.

When all tasks are done, give the user a few manual commands they can run to smoke-test the feature. 