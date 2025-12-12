# Agents Development Status

> Last Updated: 2025-12-12
> Total Agents: 5 Planned | 3 Implemented | 0 Production-Ready

## Architecture Overview

```
+-----------------------------------------------------------+
|                    ORCHESTRATOR AGENT                      |
|  - Manages application queue                               |
|  - Routes tasks to specialized agents                      |
|  - Handles errors and retries                              |
+-----------------------------------------------------------+
        |              |              |              |
        v              v              v              v
+-------------+ +-------------+ +-------------+ +-------------+
| CV ADAPTER  | | COVER       | | EMAIL       | | FORM        |
| AGENT       | | LETTER      | | PARSER      | | FILLER      |
| [DONE]      | | AGENT       | | AGENT       | | AGENT       |
|             | | [DONE]      | | [DONE]      | | [PLANNED]   |
+-------------+ +-------------+ +-------------+ +-------------+
```

---

## Agent Registry

| Agent ID | Name | Status | Priority | File |
|----------|------|--------|----------|------|
| AGT-001 | Orchestrator | Planned | P1 | src/agents/orchestrator.py |
| AGT-002 | CV Adapter | **Implemented** | P0 | src/agents/cv_adapter.py |
| AGT-003 | Cover Letter | **Implemented** | P0 | src/agents/cv_adapter.py |
| AGT-004 | Email Parser | **Implemented** | P0 | src/agents/email_parser.py |
| AGT-005 | Form Filler | Planned | P1 | src/agents/form_filler.py |

---

## Agent Details

### AGT-002: CV Adapter Agent

**Status:** Implemented | **Priority:** P0 | **Tests:** 5 passing

**Purpose:** Adapts base CV to match specific job requirements

**Capabilities:**
- [x] Parse job description for key requirements
- [x] Match candidate skills to requirements
- [x] Reorder/emphasize relevant experience
- [x] Generate transparency report ("what we changed")
- [x] Calculate match score (0-100)
- [x] Support EN/ES languages

**Input Schema:**
```python
class CVAdapterInput(BaseModel):
    base_cv: str           # Original CV content
    job_description: str   # Full JD text
    job_title: str
    company: str
    language: str = "en"   # en | es
```

**Output Schema:**
```python
class CVAdapterOutput(BaseModel):
    adapted_cv: str
    match_score: int       # 0-100
    changes_made: list[str]
    skills_matched: list[str]
    skills_missing: list[str]
    key_highlights: list[str]
```

**Test Results:**
| Test Case | Result | Date | Notes |
|-----------|--------|------|-------|
| Properties validation | Pass | 2025-12-11 | name, model, max_tokens |
| Input validation | Pass | 2025-12-11 | Pydantic validation |
| Output validation | Pass | 2025-12-11 | Pydantic validation |
| Mocked run | Pass | 2025-12-11 | With mock Claude |
| Spanish language | Pass | 2025-12-11 | Language switch |

---

### AGT-003: Cover Letter Generator Agent

**Status:** Implemented | **Priority:** P0 | **Tests:** 3 passing

**Purpose:** Generate personalized cover letters per job

**Capabilities:**
- [x] Extract company values/mission from JD
- [x] Match candidate experience to role
- [x] Generate concise cover letter
- [x] Support EN/ES languages
- [x] Generate talking points

**Input Schema:**
```python
class CoverLetterInput(BaseModel):
    cv_content: str        # Adapted CV content
    job_description: str
    job_title: str
    company: str
    language: str = "en"
```

**Output Schema:**
```python
class CoverLetterOutput(BaseModel):
    cover_letter: str
    talking_points: list[str]
```

**Test Results:**
| Test Case | Result | Date | Notes |
|-----------|--------|------|-------|
| Properties validation | Pass | 2025-12-11 | name, model, max_tokens |
| Input validation | Pass | 2025-12-11 | Pydantic validation |
| Output validation | Pass | 2025-12-11 | Pydantic validation |

---

### AGT-004: Email Parser Agent

**Status:** Implemented | **Priority:** P0 | **Tests:** 14 passing

**Purpose:** Extract job offers from email notifications

**Capabilities:**
- [x] Parse HTML/text email content
- [x] Extract multiple jobs per email (newsletters)
- [x] Identify source platform
- [x] Calculate extraction confidence
- [x] Batch processing support

**Input Schema:**
```python
class EmailContent(BaseModel):
    subject: str
    sender: str
    body: str
    received_at: str
    message_id: str | None = None

class EmailParserInput(BaseModel):
    email: EmailContent
    extract_all: bool = True
```

**Output Schema:**
```python
class ExtractedJob(BaseModel):
    title: str
    company: str
    location: str | None
    job_url: str
    source_platform: str
    salary_range: str | None
    job_type: str | None
    brief_description: str | None

class EmailParserOutput(BaseModel):
    jobs: list[ExtractedJob]
    source_platform: str
    is_job_alert: bool
    confidence: float  # 0-1
    raw_job_count: int
```

**Gmail Integration:** Done (OAuth Desktop App)

**Supported Sources:**
| Source | Status | Notes |
|--------|--------|-------|
| LinkedIn Job Alerts | Ready | HTML parsing implemented |
| Indeed | Ready | Digest format supported |
| InfoJobs | Ready | Spanish market |
| Jack & Jill | Ready | Direct links |
| Glassdoor | Ready | Similar to LinkedIn |
| Recruiter emails | Ready | Single opportunity |

**Gmail CLI Commands:**
- `gmail-login` - OAuth authentication flow
- `gmail-status` - Check connection status
- `gmail-logout` - Remove stored token
- `gmail-fetch --max N` - Fetch job alert emails

**Test Results:**
| Test Case | Result | Date | Notes |
|-----------|--------|------|-------|
| Agent properties | Pass | 2025-12-11 | name, model, max_tokens |
| Email content validation | Pass | 2025-12-11 | All fields |
| Optional message_id | Pass | 2025-12-11 | Null handling |
| Extracted job full | Pass | 2025-12-11 | All fields |
| Extracted job minimal | Pass | 2025-12-11 | Required only |
| Parser input | Pass | 2025-12-11 | Validation |
| Parser output | Pass | 2025-12-11 | Validation |
| Confidence bounds | Pass | 2025-12-11 | 0-1 range |
| Mocked run | Pass | 2025-12-11 | With mock Claude |
| Batch properties | Pass | 2025-12-11 | Batch agent |
| Batch input | Pass | 2025-12-11 | Multiple emails |
| Batch output | Pass | 2025-12-11 | Aggregated results |
| Prompt metadata | Pass | 2025-12-11 | Contains email info |
| System prompt | Pass | 2025-12-11 | Key instructions |

---

### AGT-005: Form Filler Agent

**Status:** Planned | **Priority:** P1

**Purpose:** Automate job application form completion via MCP

**Supported ATS:**
| Platform | Status | Success Rate | Notes |
|----------|--------|--------------|-------|
| Breezy.hr | POC Done | 100% | JS workaround needed |
| Workable | Blocked | 0% | CAPTCHA |
| Lever | Blocked | 0% | hCaptcha |
| BambooHR | Blocked | 0% | File upload |

---

### AGT-001: Orchestrator Agent

**Status:** Planned | **Priority:** P1

**Purpose:** Coordinates all agents in the pipeline

**State Machine:**
```
INBOX -> PARSING -> ADAPTING -> READY -> APPLYING -> COMPLETED
                                    \-> BLOCKED
```

---

## Performance Metrics

| Agent | Avg Latency | Token Usage | Success Rate | Cost/Call |
|-------|-------------|-------------|--------------|-----------|
| CV Adapter | ~2-3s | ~1500 | TBD | ~$0.02 |
| Cover Letter | ~2-3s | ~1000 | TBD | ~$0.015 |
| Email Parser | ~1-2s | ~800 | TBD | ~$0.01 |
| Form Filler | - | - | 12.5% (POC) | - |

---

## Development Backlog

| Priority | Agent | Task | Status |
|----------|-------|------|--------|
| P0 | Base | Implement BaseAgent with Langfuse | **Done** |
| P0 | CV Adapter | Full implementation | **Done** |
| P0 | Cover Letter | Full implementation | **Done** |
| P0 | Email Parser | Core implementation | **Done** |
| P0 | Email Parser | Gmail API integration | **Done** |
| P1 | Form Filler | MCP integration | Todo |
| P1 | Orchestrator | LangGraph state machine | Todo |
