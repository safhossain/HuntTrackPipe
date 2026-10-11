"""The fixed Jev question set (DESIGN.md section 6) and its mapping to Excel.

Question keys are internal; Jev never sees them. ``EXISTENCE`` keys gate LLM
schema fields, ``CHOICE_COLUMNS`` map choice keys to Excel columns + values.
"""
from __future__ import annotations

# Ordered as the Excel columns are. value = LLM schema field name.
EXISTENCE: dict[str, str] = {
    "has_requisition_id": "requisition_id",
    "has_organization": "organization",
    "has_position_title": "position_title",
    "has_compensation": "compensation",
    "has_deadline": "deadline",
    "has_recruiter_name": "recruiter_name",
    "has_recruiter_contact": "recruiter_contact",
    "has_role_categories": "role_categories",
    "has_position_level": "position_level",
}

DOC_NOULS: dict[str, str] = {
    "requires_cover_letter": "CoverLetter",
    "requires_transcript": "Transcript",
    "requires_portfolio": "Portfolio",
    "requires_references": "References",
}

WORK_MODE_VALUES: dict[str, str] = {
    "in_person": "In-person",
    "hybrid": "Hybrid",
    "remote": "Remote",
    "travel": "Travel",
    "tbd": "TBD",
    "unknown": "Unknown",
}

EMPLOYMENT_TYPE_VALUES: dict[str, str] = {
    "full_time": "Full-time",
    "part_time": "Part-time",
    "contract": "Contract",
    "contract_full_time": "Contract Full-Time",
    "contract_part_time": "Contract Part-Time",
    "internship": "Internship",
    "co_op": "Co-op",
    "temporary": "Temporary",
    "freelance": "Freelance",
    "unknown": "Unknown",
}

# choice key -> (Excel column, LLM schema field, option -> Excel value)
CHOICE_COLUMNS: dict[str, tuple[str, str, dict[str, str]]] = {
    "work_mode": ("Work_Mode", "work_mode", WORK_MODE_VALUES),
    "employment_type": ("Employment_Type", "employment_type", EMPLOYMENT_TYPE_VALUES),
}

UPLOAD_MODES = ("single_document", "separate_uploads", "single_combined_file", "not_stated")


def _noul(instructions: str, true: str, false: str) -> dict:
    return {"type": "noul", "instructions": instructions, "criteria": {"true": true, "false": false}}


def _choice(instructions: str, criteria: dict[str, str]) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


QUESTIONS: dict[str, dict] = {
    "is_job_posting": _noul(
        "The text is a job posting or job advertisement for a specific role.",
        "Describes a role to hire for: responsibilities, requirements, how to apply",
        "An article, resume, email thread, or unrelated text",
    ),
    "has_requisition_id": _noul(
        "The posting states an explicit requisition, job, or reference ID for this role.",
        "An explicit identifier such as 'Req ID 12345', 'R-98765', 'JR0012', 'Job ID: 4567', 'Reference: 2026-ENG-17'",
        "No such identifier; salary figures, years of experience, phone numbers or dates do not count",
    ),
    "has_organization": _noul(
        "The name of the hiring organization can be identified from the text.",
        "A company or organization is named anywhere, e.g. 'About Shopify', 'Google is hiring', 'Join RBC'",
        "Anonymous posting, a staffing agency that hides its client, or no organization named",
    ),
    "has_position_title": _noul(
        "A job title for this role is stated.",
        "A concrete title such as 'Software Engineer II', 'Junior Backend Developer', 'Data Analyst Intern'",
        "Only a team or department is mentioned, or the role is described vaguely without a title",
    ),
    "has_compensation": _noul(
        "Pay for this role is stated in numbers.",
        "A salary, hourly rate, pay range or stipend given with numbers, e.g. '$80,000-$95,000', '$35/hour'",
        "Only words like 'competitive salary' or 'commensurate with experience', or no mention of pay",
    ),
    "has_deadline": _noul(
        "An application closing date for this posting is stated.",
        "A specific date or day by which to apply, e.g. 'Apply by March 3', 'Posting closes 2026-11-01'",
        "'Open until filled', 'rolling basis', or no closing date mentioned",
    ),
    "has_recruiter_name": _noul(
        "A named contact person (recruiter, hiring manager, talent partner) appears in the text.",
        "A person's name is given as the contact for this role",
        "No individual person is named; a generic team or company name does not count",
    ),
    "has_recruiter_contact": _noul(
        "Contact details for a specific person appear in the text.",
        "An email address, phone number or LinkedIn profile belonging to a named contact",
        "Only a generic careers mailbox, a portal link, or no contact details at all",
    ),
    "has_role_categories": _noul(
        "The technical area of the role (backend, frontend, mobile, devops, data, ML, QA, embedded, etc.) can be inferred.",
        "The tech stack, responsibilities or title make the area clear",
        "The text is too generic to tell what kind of engineering or work it is",
    ),
    "has_position_level": _noul(
        "The seniority level of the role is stated or clearly inferable.",
        "Words like 'Junior', 'Senior', 'Intern', 'Lead', 'Staff', 'entry-level', or a stated years-of-experience requirement",
        "Nothing in the text indicates the level",
    ),
    "work_mode": _choice(
        "Where is this role performed?",
        {
            "in_person": "On-site / in-office only, no remote option",
            "hybrid": "Mix of office and remote days",
            "remote": "Fully remote or work-from-home",
            "travel": "Primarily travelling between client or field sites",
            "tbd": "The posting explicitly says the arrangement is to be determined or discussed",
            "unknown": "The posting does not mention where the work happens",
        },
    ),
    "employment_type": _choice(
        "What is the employment type of this role?",
        {
            "full_time": "Permanent full-time",
            "part_time": "Permanent part-time",
            "contract": "Fixed-term contract, hours not specified",
            "contract_full_time": "Fixed-term contract, full-time hours",
            "contract_part_time": "Fixed-term contract, part-time hours",
            "internship": "Internship",
            "co_op": "Co-op or work term for students",
            "temporary": "Temporary or seasonal",
            "freelance": "Freelance or gig work",
            "unknown": "The posting does not say",
        },
    ),
    "upload_mode": _choice(
        "How does the posting ask application documents to be submitted?",
        {
            "single_document": "Only a resume/CV is requested",
            "separate_uploads": "Several documents (e.g. resume and cover letter) submitted as separate files or fields",
            "single_combined_file": "Several documents must be merged into one single file before uploading",
            "not_stated": "The posting does not describe how documents are submitted",
        },
    ),
    "requires_cover_letter": _noul(
        "A cover letter is required or requested.",
        "The posting asks for a cover letter or letter of interest",
        "No cover letter mentioned, or explicitly optional/not needed",
    ),
    "requires_transcript": _noul(
        "An academic transcript is required or requested.",
        "The posting asks for a transcript or academic record",
        "No transcript mentioned",
    ),
    "requires_portfolio": _noul(
        "A portfolio, code samples or work samples are required or requested.",
        "The posting asks for a portfolio, GitHub, writing samples or similar work samples",
        "No portfolio or samples mentioned",
    ),
    "requires_references": _noul(
        "References are required at application time.",
        "The posting asks for reference letters or contact details of references with the application",
        "No references mentioned, or only 'references available on request'",
    ),
}
