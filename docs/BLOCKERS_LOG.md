# Technical Blockers Log

> Last Updated: 2025-12-12
> Active Blockers: 4 Critical | 1 Moderate | 0 Minor

## Summary Dashboard

| Category | Critical | Moderate | Resolved |
|----------|----------|----------|----------|
| CAPTCHA Systems | 2 | 0 | 0 |
| File Uploads | 1 | 0 | 0 |
| Authentication | 1 | 0 | 0 |
| Form Handling | 0 | 1 | 1 |
| Console Encoding | 0 | 0 | 1 |

---

## Critical Blockers

### BLK-001: Cloudflare Turnstile CAPTCHA

**Status:** ACTIVE | **Severity:** Critical | **Since:** 2025-12-09

**Affected Platforms:** Workable (Metova, others)

**Problem:**
Forms protected by Cloudflare Turnstile CAPTCHA block automated submission. Submit button shows "Submitting..." but never completes.

**Technical Details:**
- Platform: Workable
- CAPTCHA Type: Cloudflare Turnstile (invisible challenge)
- Detection: `cf-turnstile` div or iframe in DOM

**Attempted Solutions:**
| Solution | Result | Date |
|----------|--------|------|
| Direct form submission | Failed | 2025-12-09 |
| Wait for auto-resolve | Failed | 2025-12-09 |

**Potential Solutions:**
| Solution | Feasibility | Notes |
|----------|-------------|-------|
| Manual intervention | High | User solves CAPTCHA |
| 2captcha/Anti-Captcha | Medium | ToS concerns |
| "Apply with LinkedIn" | High | Where available |

**Current Workaround:** Request manual user intervention

---

### BLK-002: hCaptcha Puzzle Challenge

**Status:** ACTIVE | **Severity:** Critical | **Since:** 2025-12-09

**Affected Platforms:** Lever (Jobgether, others)

**Problem:**
hCaptcha presents image-based puzzle challenges that cannot be automated.

**Current Workaround:** Manual user intervention required

---

### BLK-003: File Upload Failures (BambooHR)

**Status:** ACTIVE | **Severity:** Critical | **Since:** 2025-12-09

**Affected Platforms:** BambooHR (Xerxes Global, others)

**Problem:**
Cannot programmatically upload files to BambooHR file input elements.

**Error:** `Failed to upload file. The element could not accept the file directly`

**Potential Solutions:**
| Solution | Feasibility | Notes |
|----------|-------------|-------|
| Browser extension | High | Needs extension |
| Clipboard paste | Medium | Platform dependent |
| Direct API | High | If available |

**Current Workaround:** User manually uploads CV

---

### BLK-004: Platform Login Requirements

**Status:** ACTIVE | **Severity:** Critical | **Since:** 2025-12-09

**Affected Platforms:** Jack & Jill (app.jackandjill.ai)

**Problem:**
Some job listings redirect to login page instead of application form.

**Technical Details:**
- Behavior: Redirects to `/sign-in?redirect_url=...`
- Requires: User authentication on intermediary platform

**Current Workaround:** User logs in manually before automation

---

## Moderate Blockers

### BLK-005: Multi-Step Form Handling (Phenom)

**Status:** ACTIVE | **Severity:** Moderate | **Since:** 2025-12-09

**Affected Platforms:** Phenom ATS (Sopra Steria)

**Problem:**
Complex multi-step forms require data not typically in CV (full address, phone with country code).

**Solution:** Create comprehensive user profile with all personal data fields.

**Current Workaround:** Use placeholder data

---

## Resolved Blockers

### BLK-R001: Form Interaction Timeouts (Breezy.hr)

**Status:** RESOLVED | **Resolved:** 2025-12-09

**Problem:** Native MCP click/fill methods timeout on Breezy.hr forms.

**Solution:** Use `evaluate_script` with direct JavaScript DOM manipulation.

```javascript
// Instead of native fill
await page.evaluate(() => {
  document.querySelector('#field-id').value = 'value';
  document.querySelector('#field-id').dispatchEvent(new Event('input', { bubbles: true }));
});
```

---

### BLK-R002: Rich Spinner Unicode Encoding (Windows)

**Status:** RESOLVED | **Resolved:** 2025-12-12

**Problem:** Rich Progress spinner uses Braille characters (e.g., `\u283c`, `\u2807`) that cannot be encoded by Windows cp1252 console.

**Error:**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u283c' in position 0: character maps to <undefined>
```

**Solution:** Replace Rich Progress spinner with simple text messages:

```python
# Before (broken on Windows)
with Progress(SpinnerColumn(), TextColumn(...)) as progress:
    progress.add_task("Loading...", total=None)

# After (works everywhere)
console.print("[dim]Loading...[/dim]")
```

**Files Modified:**
- `src/cli/commands.py` - Removed all SpinnerColumn usage

---

## Platform Compatibility Matrix

| Platform | Form Fill | File Upload | Submit | Status |
|----------|-----------|-------------|--------|--------|
| Breezy.hr | OK (JS) | N/A | OK | Working |
| Workable | OK | OK | Blocked | CAPTCHA |
| Lever | OK (JS) | OK | Blocked | hCaptcha |
| BambooHR | OK | Blocked | - | File upload |
| Phenom | OK | OK | Partial | Multi-step |
| Greenhouse | Unknown | Unknown | Unknown | Not tested |
| Workday | Unknown | Unknown | Unknown | Not tested |

---

## Blocker Resolution Process

1. **Identify:** Document with full technical details
2. **Research:** List potential solutions
3. **Prioritize:** Assign severity
4. **Implement:** Try solutions, document results
5. **Resolve:** Document working solution
