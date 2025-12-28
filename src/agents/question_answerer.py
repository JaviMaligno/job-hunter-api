"""Question Answerer Agent for custom ATS questions."""

import logging
from typing import Any

from pydantic import BaseModel, Field

from src.agents.base import BaseAgent
from src.automation.models import UserFormData

logger = logging.getLogger(__name__)


# ============================================================================
# Input/Output Models
# ============================================================================


class QuestionInput(BaseModel):
    """A single question to answer."""

    question_text: str
    field_type: str = "text"  # text, textarea, select, radio, checkbox
    options: list[str] | None = None  # For select/radio/checkbox
    max_length: int | None = None
    required: bool = True


class QuestionAnswer(BaseModel):
    """Answer to a question."""

    question_text: str
    answer: str
    confidence: float = Field(ge=0.0, le=1.0)  # 0-1 confidence score
    reasoning: str | None = None


class QuestionAnswererInput(BaseModel):
    """Input for Question Answerer Agent."""

    questions: list[QuestionInput]
    user_data: UserFormData
    cv_content: str
    job_description: str | None = None
    job_title: str | None = None
    company: str | None = None
    cover_letter: str | None = None


class QuestionAnswererOutput(BaseModel):
    """Output from Question Answerer Agent."""

    answers: list[QuestionAnswer]
    unanswered: list[str] = Field(default_factory=list)  # Questions that couldn't be answered


# ============================================================================
# Question Answerer Agent
# ============================================================================


class QuestionAnswererAgent(BaseAgent[QuestionAnswererOutput]):
    """Agent for answering custom ATS application questions.

    Uses the user's CV, cover letter, and personal data to generate
    appropriate answers for custom questions on job applications.
    """

    @property
    def name(self) -> str:
        return "question-answerer"

    @property
    def system_prompt(self) -> str:
        return """You are an expert at answering job application questions.
Your role is to help candidates answer custom questions on job applications by:

1. Using information from their CV and cover letter
2. Drawing on their stated skills, experience, and qualifications
3. Maintaining consistency with their professional profile
4. Being honest and accurate - never fabricating experience or credentials
5. Adapting answers to the specific job and company context

Guidelines:
- Keep answers concise but complete
- Use professional language
- Be specific and provide examples when relevant
- For yes/no questions, answer directly then elaborate if needed
- For multiple choice, select the most accurate option
- For open-ended questions, focus on relevant experience
- Match the tone to the company culture if known

If you cannot answer a question based on the provided information:
- Indicate low confidence
- Suggest the user should provide their own answer
- Never make up qualifications or experience"""

    async def _execute(
        self, input_data: QuestionAnswererInput, **kwargs: Any
    ) -> QuestionAnswererOutput:
        """Generate answers for custom application questions."""
        answers = []
        unanswered = []

        for question in input_data.questions:
            try:
                answer = await self._answer_question(question, input_data)
                if answer.confidence < 0.3:
                    unanswered.append(question.question_text)
                answers.append(answer)
            except Exception as e:
                logger.error(f"Failed to answer question: {e}")
                unanswered.append(question.question_text)
                answers.append(
                    QuestionAnswer(
                        question_text=question.question_text,
                        answer="",
                        confidence=0.0,
                        reasoning=f"Error: {e}",
                    )
                )

        return QuestionAnswererOutput(
            answers=answers,
            unanswered=unanswered,
        )

    async def _answer_question(
        self, question: QuestionInput, context: QuestionAnswererInput
    ) -> QuestionAnswer:
        """Answer a single question."""
        # Build context for the question
        context_parts = []

        if context.job_title:
            context_parts.append(f"Job Title: {context.job_title}")
        if context.company:
            context_parts.append(f"Company: {context.company}")
        if context.job_description:
            context_parts.append(f"Job Description:\n{context.job_description[:2000]}")

        context_parts.append("\nCandidate Profile:")
        context_parts.append(f"Name: {context.user_data.first_name} {context.user_data.last_name}")
        if context.user_data.current_title:
            context_parts.append(f"Current Title: {context.user_data.current_title}")
        if context.user_data.years_experience:
            context_parts.append(f"Years of Experience: {context.user_data.years_experience}")
        if context.user_data.skills:
            context_parts.append(f"Skills: {', '.join(context.user_data.skills)}")

        if context.cv_content:
            context_parts.append(f"\nCV Content:\n{context.cv_content[:3000]}")

        if context.cover_letter:
            context_parts.append(f"\nCover Letter:\n{context.cover_letter[:1500]}")

        context_str = "\n".join(context_parts)

        # Build the prompt
        prompt = f"""Based on the following context, answer this application question:

{context_str}

---
QUESTION: {question.question_text}
Type: {question.field_type}
"""
        if question.options:
            prompt += f"Options: {', '.join(question.options)}\n"
        if question.max_length:
            prompt += f"Max Length: {question.max_length} characters\n"
        prompt += f"Required: {'Yes' if question.required else 'No'}\n"

        prompt += """
---
Provide your answer in the following JSON format:
{
    "answer": "Your answer here",
    "confidence": 0.8,
    "reasoning": "Brief explanation of why this answer is appropriate"
}

For select/radio questions, choose the best option from the provided choices.
For checkbox questions, list selected options separated by commas.
For text/textarea, provide a natural language answer."""

        # Call Claude
        response = await self._call_claude(prompt)

        # Parse response
        import json

        try:
            # Extract JSON from response
            clean_response = response.strip()
            if clean_response.startswith("```"):
                lines = clean_response.split("\n")
                clean_response = "\n".join(
                    lines[1:-1] if lines[-1].startswith("```") else lines[1:]
                )

            # Find JSON object
            start = clean_response.find("{")
            end = clean_response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = clean_response[start:end]
                data = json.loads(json_str)

                return QuestionAnswer(
                    question_text=question.question_text,
                    answer=str(data.get("answer", "")),
                    confidence=float(data.get("confidence", 0.5)),
                    reasoning=data.get("reasoning"),
                )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse JSON response: {e}")

        # Fallback: use raw response as answer
        return QuestionAnswer(
            question_text=question.question_text,
            answer=response.strip()[:500],  # Limit length
            confidence=0.5,
            reasoning="Parsed from raw response",
        )


# ============================================================================
# Batch Question Answering
# ============================================================================


async def answer_questions_batch(
    questions: list[dict],
    user_data: UserFormData,
    cv_content: str,
    job_description: str | None = None,
    job_title: str | None = None,
    company: str | None = None,
    cover_letter: str | None = None,
    claude_api_key: str | None = None,
) -> dict[str, str]:
    """Convenience function to answer a batch of questions.

    Args:
        questions: List of question dicts with 'text', 'type', 'options' keys
        user_data: User's personal data
        cv_content: User's CV content
        job_description: Optional job description
        job_title: Optional job title
        company: Optional company name
        cover_letter: Optional cover letter
        claude_api_key: Optional Claude API key

    Returns:
        Dict mapping question text to answer
    """
    agent = QuestionAnswererAgent(claude_api_key=claude_api_key)

    question_inputs = [
        QuestionInput(
            question_text=q.get("text", q.get("question", "")),
            field_type=q.get("type", "text"),
            options=q.get("options"),
            max_length=q.get("max_length"),
            required=q.get("required", True),
        )
        for q in questions
    ]

    input_data = QuestionAnswererInput(
        questions=question_inputs,
        user_data=user_data,
        cv_content=cv_content,
        job_description=job_description,
        job_title=job_title,
        company=company,
        cover_letter=cover_letter,
    )

    result = await agent.run(input_data)

    return {answer.question_text: answer.answer for answer in result.answers}
