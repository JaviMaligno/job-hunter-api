"""CV Adapter Agent - Adapts CVs to match job requirements."""

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent


class CVAdapterInput(BaseModel):
    """Input for CV adaptation."""

    base_cv: str = Field(description="Original CV content in text/markdown format")
    job_description: str = Field(description="Full job description text")
    job_title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    language: str | None = Field(default=None, description="Output language override: 'en' or 'es'. If None, auto-detect from job description.")


class CVAdapterOutput(BaseModel):
    """Output from CV adaptation."""

    detected_language: str = Field(description="Detected language of job description: 'en' or 'es'")
    adapted_cv: str = Field(description="Adapted CV content optimized for the job")
    match_score: int = Field(ge=0, le=100, description="Match score 0-100")
    changes_made: list[str] = Field(description="List of changes made to the CV")
    skills_matched: list[str] = Field(description="Skills that match the job requirements")
    skills_missing: list[str] = Field(description="Required skills not found in CV")
    key_highlights: list[str] = Field(description="Key points to emphasize in interview")


CV_ADAPTER_SYSTEM_PROMPT = """You are an expert CV optimization specialist. Your task is to adapt CVs to match specific job requirements while maintaining honesty and accuracy.

## Guidelines:

1. **Never invent experience or skills** - Only emphasize and reorder existing content
2. **Highlight relevant experience** - Move the most relevant roles and achievements to prominent positions
3. **Use keywords from the JD** - Mirror the language and terminology used in the job description
4. **Quantify achievements** - Emphasize metrics and concrete results where available
5. **Tailor the summary** - Adjust the professional summary to align with the role
6. **Be concise** - Keep the CV focused and readable

## For Spanish CVs:
- Use formal language (usted form implied)
- Consider European vs Latin American conventions based on context
- Include photo placeholder only if targeting Spain/DACH regions

## Match Score Criteria:
- 90-100: Excellent match - candidate exceeds requirements
- 70-89: Good match - candidate meets most requirements
- 50-69: Moderate match - candidate meets some requirements, notable gaps
- Below 50: Poor match - significant skill/experience gaps

## Output Format:
Return a JSON object with the adapted CV and analysis."""


class CVAdapterAgent(BaseAgent[CVAdapterOutput]):
    """Agent that adapts CVs to match job requirements."""

    @property
    def name(self) -> str:
        return "cv-adapter"

    @property
    def system_prompt(self) -> str:
        return CV_ADAPTER_SYSTEM_PROMPT

    async def _execute(self, input_data: CVAdapterInput, **kwargs) -> CVAdapterOutput:
        """
        Adapt a CV for a specific job.

        Args:
            input_data: CV and job information.

        Returns:
            Adapted CV with analysis.
        """
        # Build language instruction
        if input_data.language:
            language_instruction = f"""Output language: {input_data.language.upper()} (user specified)
Set detected_language to "{input_data.language}" in your response."""
        else:
            language_instruction = """IMPORTANT: First, detect the language of the job description.
- If the job description is in Spanish, set detected_language to "es" and generate ALL output in Spanish.
- If the job description is in English (or any other language), set detected_language to "en" and generate ALL output in English.
The adapted CV, changes_made, skills_matched, skills_missing, and key_highlights should ALL be in the detected language."""

        prompt = f"""Please adapt the following CV for this job opportunity.

## Job Details
**Title:** {input_data.job_title}
**Company:** {input_data.company}

### Job Description:
{input_data.job_description}

---

## Original CV:
{input_data.base_cv}

---

## Task:
1. **Detect the language** of the job description first
2. Analyze the job requirements
3. Identify matching skills and experience in the CV
4. Identify missing skills or gaps
5. Create an adapted version of the CV that:
   - Reorders sections to highlight relevant experience
   - Emphasizes matching skills and achievements
   - Uses keywords from the job description
   - Maintains all factual information (no inventions)
6. Calculate a match score (0-100)
7. List key points for interview preparation

{language_instruction}

Return your analysis as a JSON object with detected_language as the first field."""

        return await self._call_claude_json(
            prompt=prompt,
            output_model=CVAdapterOutput,
        )


class CoverLetterInput(BaseModel):
    """Input for cover letter generation."""

    cv_content: str = Field(description="CV content (original or adapted)")
    job_description: str = Field(description="Full job description")
    job_title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    language: str = Field(default="en", description="Output language: 'en' or 'es' (should use detected_language from CV adapter)")
    tone: str = Field(
        default="professional", description="Tone: professional, enthusiastic, casual"
    )


class CoverLetterOutput(BaseModel):
    """Output from cover letter generation."""

    cover_letter: str = Field(description="Generated cover letter")
    key_points: list[str] = Field(description="Key points addressed in the letter")
    talking_points: list[str] = Field(description="Interview talking points based on the letter")


COVER_LETTER_SYSTEM_PROMPT = """You are an expert cover letter writer. Create compelling, personalized cover letters that connect candidate experience to job requirements.

## Guidelines:

1. **Be specific** - Reference specific requirements from the JD and how the candidate meets them
2. **Show enthusiasm** - Demonstrate genuine interest in the company and role
3. **Keep it concise** - 3-4 paragraphs maximum
4. **Include a hook** - Start with something memorable
5. **Call to action** - End with a clear next step

## Structure:
- Opening: Hook + role you're applying for
- Body: 1-2 paragraphs connecting your experience to their needs
- Closing: Enthusiasm + call to action

## For Spanish:
- Use appropriate formality (Estimado/a...)
- Adapt to regional conventions"""


class CoverLetterAgent(BaseAgent[CoverLetterOutput]):
    """Agent that generates cover letters."""

    @property
    def name(self) -> str:
        return "cover-letter"

    @property
    def system_prompt(self) -> str:
        return COVER_LETTER_SYSTEM_PROMPT

    async def _execute(self, input_data: CoverLetterInput, **kwargs) -> CoverLetterOutput:
        """
        Generate a cover letter for a job application.

        Args:
            input_data: CV and job information.

        Returns:
            Generated cover letter with talking points.
        """
        prompt = f"""Generate a cover letter for this job application.

## Job Details
**Title:** {input_data.job_title}
**Company:** {input_data.company}

### Job Description:
{input_data.job_description}

---

## Candidate's CV:
{input_data.cv_content}

---

## Requirements:
- Language: {input_data.language.upper()}
- Tone: {input_data.tone}
- Length: 3-4 paragraphs
- Focus on the most relevant experience and skills

Return a JSON object with the cover letter, key points addressed, and interview talking points."""

        return await self._call_claude_json(
            prompt=prompt,
            output_model=CoverLetterOutput,
        )
