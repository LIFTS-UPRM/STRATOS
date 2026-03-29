---
name: AI / RAG Task
about: LLM, retrieval, or tool-calling work
title: "[AI] "
labels: ["ai"]
assignees: []
---

## Objective
What AI capability is being implemented?

## Inputs
What does the system receive?
- Query:
- Context (if any):
- Tool inputs (if applicable):

## Outputs
Define expected structure:

```json
{
  "type": "",
  "summary": "",
  "data": {},
  "sources": []
}
```

## Tasks

- [ ] Implement logic
- [ ] Integrate with /chat
- [ ] Validate outputs

## Acceptance Criteria

- [ ] Output follows schema
- [ ] No hallucination when context exists
- [ ] Correct tool is triggered when needed
- [ ] Responses are deterministic enough for demo

## Edge Cases
- No context found
- Tool failure
- Ambiguous query

## Dependencies
- #

## Notes

Prompt design, model choice, constraints, etc.