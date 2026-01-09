"""Skill Enhancer Agent - Adds skills to CVs based on user explanations."""

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent


class SkillEnhancerInput(BaseModel):
    """Input for skill enhancement."""

    current_cv: str = Field(description="The current CV content in text/markdown format")
    skill_name: str = Field(description="The skill to add to the CV")
    user_explanation: str = Field(
        description="User's explanation of their experience with the skill"
    )
    language: str | None = Field(
        default=None,
        description="Output language: 'en' or 'es'. If None, auto-detect from CV.",
    )


class SkillEnhancerOutput(BaseModel):
    """Output from skill enhancement."""

    enhanced_cv: str = Field(description="The CV with the skill added")
    changes_made: list[str] = Field(description="List of changes made to the CV")
    change_explanation: str = Field(
        description="Explanation of where and how the skill was added"
    )


SKILL_ENHANCER_SYSTEM_PROMPT = """You are an expert CV enhancement specialist. Your task is to naturally integrate new skills into existing CVs based on the user's explanation of their experience.

## Core Principles:

1. **Never invent experience** - Only use information provided by the user in their explanation
2. **Find the right section** - Identify the most appropriate place in the CV to add the skill
3. **Maintain consistency** - Match the CV's existing format, style, and tone
4. **Write naturally** - Create professional text that flows with the rest of the CV
5. **Be accurate** - Only describe what the user has actually explained

## Guidelines for Adding Skills:

### Finding the Right Location:
- If the CV has a "Skills" or "Technical Skills" section, add the skill there
- If the experience relates to a specific job, add it to that job's description
- If it's a soft skill or certification, find or create an appropriate section
- Consider adding to multiple sections if relevant (e.g., skills list AND job description)

### Writing Style:
- Match the verb tense used in the CV (past tense for previous roles, present for current)
- Use action verbs and quantify where possible based on user's explanation
- Keep descriptions concise and impactful
- Mirror the level of detail in existing CV entries

### What NOT to Do:
- Do not add experience the user did not describe
- Do not exaggerate or embellish the user's explanation
- Do not remove or significantly alter existing content
- Do not change the overall structure of the CV
- Do not add generic filler text

## For Spanish CVs:
- Use formal language appropriate for professional documents
- Adapt terminology to Spanish-speaking conventions
- Use appropriate verb conjugations

## Output:
Return a JSON object with:
- enhanced_cv: The complete CV with the skill integrated
- changes_made: A list of specific changes (e.g., "Added Python to Technical Skills section")
- change_explanation: A brief explanation of your reasoning for placement and wording"""


class SkillEnhancerAgent(BaseAgent[SkillEnhancerOutput]):
    """Agent that adds skills to CVs based on user explanations."""

    @property
    def name(self) -> str:
        return "skill-enhancer"

    @property
    def system_prompt(self) -> str:
        return SKILL_ENHANCER_SYSTEM_PROMPT

    async def _execute(
        self, input_data: SkillEnhancerInput, **kwargs
    ) -> SkillEnhancerOutput:
        """
        Add a skill to a CV based on user explanation.

        Args:
            input_data: CV content, skill name, and user explanation.

        Returns:
            Enhanced CV with changes tracked.
        """
        # Build language instruction
        if input_data.language:
            language_instruction = f"""Output language: {input_data.language.upper()} (user specified)
Generate the enhanced CV and all explanations in {input_data.language.upper()}."""
        else:
            language_instruction = """Language: Auto-detect from the CV content.
- If the CV is in Spanish, generate all output in Spanish.
- If the CV is in English (or any other language), generate all output in English.
Maintain the same language throughout the enhanced CV."""

        prompt = f"""Please add the following skill to the CV based on the user's explanation of their experience.

## Skill to Add
**Skill Name:** {input_data.skill_name}

## User's Explanation of Their Experience
{input_data.user_explanation}

---

## Current CV
{input_data.current_cv}

---

## Task
1. Analyze the CV structure to identify the best location(s) to add this skill
2. Based ONLY on the user's explanation, write professional CV content for this skill
3. Integrate the skill naturally into the CV
4. Track all changes made
5. Explain your reasoning for the placement and wording

## Important Rules
- ONLY use information from the user's explanation - do not invent any details
- Maintain the CV's existing format and style
- If the user's explanation is vague, keep the CV entry concise rather than adding assumptions
- Ensure the addition looks natural and professional

{language_instruction}

Return your response as a JSON object with enhanced_cv, changes_made, and change_explanation."""

        return await self._call_claude_json(
            prompt=prompt,
            output_model=SkillEnhancerOutput,
        )
