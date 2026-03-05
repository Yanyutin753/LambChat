---
name: skill-creator
description: Create new skills, modify and improve existing skills, and measure skill performance. TRIGGER when user says "create a skill", "new skill", "make a skill", "add a skill", "edit skill", "update skill", "run evals to test a skill", "benchmark skill performance", or describes wanting to add new capabilities to the AI assistant.
---

# Skill Creator

Help users create high-quality skills for LambChat.

## When This Skill Triggers

- User wants to create a new skill
- User wants to modify an existing skill
- User wants to optimize skill descriptions
- User wants to run evals to test a skill
- User wants to benchmark skill performance
- User asks about how skills work

## Overview

The skill creation process follows this flow:

1. **Understand Requirements** - What should the skill do?
2. **Design the Skill** - Create SKILL.md and supporting files
3. **Test & Evaluate** - Run test cases and collect feedback
4. **Iterate & Improve** - Refine based on results
5. **Mount & Package** - Add to user's skill list

---

## Phase 1: Understand Requirements

Ask the user these questions (if not already answered):

1. **What should this skill do?** - Describe the capability in one sentence
2. **When should it trigger?** - What phrases or situations should activate it?
3. **What's the expected output?** - What should the AI produce?
4. **Any examples?** - Can you show an example input and output?
5. **Need test cases?** - Skills with objectively verifiable outputs (file transforms, data extraction, code generation) benefit from test cases. Skills with subjective outputs (writing style, design) often don't.

---

## Phase 2: Design the Skill

### Skill Directory Structure

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons)
```

### SKILL.md Template

```markdown
---
name: skill-name
description: [What it does]. TRIGGER when [specific phrases/situations].
---

# [Skill Name]

[One sentence overview of what this skill does]

## When to Use

[List specific trigger phrases and situations]

## Instructions

[Step-by-step instructions for the AI to follow]

## Output Format

[Describe the expected output format]

## Examples

### Example 1
**Input:** [user input]
**Output:** [expected AI output]
```

### Writing Effective Descriptions

The description is the PRIMARY way skills get triggered. Write it carefully:

**Good Description Pattern:**
```
[What it does]. TRIGGER when [specific phrases/situations].
```

**Examples:**

| Bad | Good |
|-----|------|
| "A skill for helping with code" | "Help users refactor Python code for better readability. TRIGGER when user says 'refactor', 'clean up code', 'improve code quality', or asks to make code more readable." |
| "Documentation helper" | "Generate API documentation from code comments. TRIGGER when user asks to 'generate docs', 'create API documentation', 'document this function', or 'write documentation'." |

**Tip:** Claude tends to "undertrigger" skills. Make descriptions slightly "pushy" - include related contexts where the skill would be useful even if the user doesn't explicitly name it.

### Progressive Disclosure

Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context when skill triggers (<500 lines ideal)
3. **Bundled resources** - As needed (unlimited, scripts can execute without loading)

**Key patterns:**
- Keep SKILL.md under 500 lines
- Reference files clearly with guidance on when to read them
- For large reference files (>300 lines), include a table of contents

### Writing Style

- Prefer imperative form in instructions
- Explain the **why** behind instructions, not just what to do
- Avoid heavy-handed MUSTs/ALWAYS - explain reasoning instead
- Use theory of mind - make the skill general, not tied to specific examples

---

## Phase 3: Test & Evaluate

### Quick Testing (Simple Flow)

For straightforward skills:

1. Show the complete skill content to the user
2. Ask the user to test it by simulating behavior:
   - "You can test this skill now by asking me questions that should trigger it"
   - "I'll act as if the skill is already loaded"
3. Collect feedback and iterate

### Rigorous Testing (With Evals)

For skills requiring validation:

#### Step 1: Create Test Cases

Create `evals/evals.json` in the skill directory:

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's task prompt",
      "expected_output": "Description of expected result",
      "files": [],
      "expectations": [
        "The output includes X",
        "The skill used script Y"
      ]
    }
  ]
}
```

**Good expectations are:**
- Objectively verifiable
- Descriptive (clear in benchmark viewer)
- Discriminating (pass when skill succeeds, fail when it doesn't)

#### Step 2: Run Tests

Create a workspace directory for results:
```
<skill-name>-workspace/
├── iteration-1/
│   ├── eval-1/
│   │   ├── with_skill/outputs/
│   │   └── without_skill/outputs/
│   └── benchmark.json
└── feedback.json
```

For each test case:
1. Run with skill loaded
2. Run without skill (baseline comparison)
3. Capture timing data

#### Step 3: Evaluate Results

Grade each expectation against outputs:

```json
{
  "expectations": [
    {
      "text": "The output includes X",
      "passed": true,
      "evidence": "Found in output: '...'"
    }
  ],
  "summary": {
    "passed": 2,
    "failed": 1,
    "total": 3,
    "pass_rate": 0.67
  }
}
```

#### Step 4: Analyze & Report

Look for patterns:
- **Non-discriminating expectations**: Pass regardless of skill (remove or improve)
- **High-variance evals**: Possibly flaky (investigate)
- **Skill value**: Compare with_skill vs without_skill pass rates

---

## Phase 4: Iterate & Improve

### How to Think About Improvements

1. **Generalize from feedback** - Don't overfit to specific test cases
2. **Keep instructions lean** - Remove things that aren't pulling their weight
3. **Explain the why** - Help the model understand reasoning
4. **Look for repeated work** - If test runs all write similar helper scripts, bundle them

### The Iteration Loop

1. Apply improvements to the skill
2. Rerun test cases into new iteration directory
3. Compare with previous iteration
4. Collect user feedback
5. Repeat until:
   - User says they're happy
   - Feedback is all positive
   - Not making meaningful progress

### Common Issues and Fixes

| Issue | Fix |
|-------|-----|
| Skill doesn't trigger | Add more trigger keywords to description |
| Triggers too often | Make description more specific |
| Wrong output format | Add explicit output format section with examples |
| Confuses with other skills | Add unique trigger phrases |
| Inconsistent behavior | Add clearer step-by-step instructions |
| Missing edge cases | Add examples for edge cases |

---

## Phase 5: Mount & Package

### Mounting Skills in LambChat

**IMPORTANT: Only mount after user confirms the skill works well!**

Ask the user:
```
"Would you like me to add this skill to your skills list? I can use add_skill_from_path to mount it."
```

If user says yes, call:
```
add_skill_from_path(skill_path="path/to/skill-folder")
```

The tool will:
1. Read all files in the skill directory
2. Parse SKILL.md for name and description
3. Store the skill in the user's skill list
4. Frontend will auto-refresh

### Skill Validation

Before mounting, verify using the validation script:

```bash
python scripts/quick_validate.py <skill-directory>
```

**Validation Checklist:**
- [ ] SKILL.md exists and starts with YAML frontmatter
- [ ] `name` field is kebab-case (lowercase, hyphens only)
- [ ] `name` is 64 characters or less
- [ ] `description` includes trigger keywords
- [ ] `description` is 1024 characters or less
- [ ] No angle brackets (`<` or `>`) in description
- [ ] Skill body has clear instructions
- [ ] Examples provided if complex output

---

## Advanced: Description Optimization

The description field determines whether Claude invokes a skill. After creating a skill, offer to optimize it.

### Generate Trigger Eval Queries

Create 10-20 eval queries - mix of should-trigger and should-not-trigger:

```json
[
  {"query": "the user prompt", "should_trigger": true},
  {"query": "another prompt", "should_trigger": false}
]
```

**Good queries are:**
- Realistic (what a user would actually type)
- Specific (file paths, context, details)
- Edge cases (not clear-cut)

**For should-trigger:**
- Different phrasings of the same intent
- Cases where user doesn't explicitly name the skill
- Uncommon use cases

**For should-not-trigger:**
- Near-misses (share keywords but need something different)
- Adjacent domains
- Ambiguous phrasing

### Review with User

Present queries for review, collect feedback, then iterate on the description.

---

## Reference Files

See the following for more details:

- `scripts/quick_validate.py` - Skill validation script
- `references/schemas.md` - JSON schemas for evals, grading, benchmarks

---

## Quick Reference

### Creating a Skill (Simple Flow)

1. Understand requirements (4 questions)
2. Write SKILL.md with template
3. Show to user, simulate behavior
4. Iterate based on feedback
5. Mount with `add_skill_from_path`

### Creating a Skill (Rigorous Flow)

1. Understand requirements
2. Write SKILL.md
3. Create evals/evals.json with test cases
4. Run tests (with_skill + without_skill)
5. Evaluate results
6. Iterate until satisfied
7. Optimize description
8. Mount with `add_skill_from_path`

---

Ready to create a skill? Tell me what you want the skill to do, and I'll guide you through the process.
