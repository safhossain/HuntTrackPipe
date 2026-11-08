"""The fixed Jev question set (DESIGN.md section 6) and its mapping to Excel.

Question keys are internal; Jev never sees them. ``EXISTENCE`` keys gate LLM
schema fields, ``CHOICE_COLUMNS`` map choice keys to Excel columns + values.
"""
from __future__ import annotations

# Ordered roughly as the Excel columns are. value = LLM schema field name.
EXISTENCE: dict[str, str] = {
    "has_requisition_id": "requisition_id",
    "has_organization": "organization",
    "has_position_title": "position_title",
    "has_location_country": "location_country",
    "has_location_city": "location_city",
    "has_compensation": "compensation",
    "has_deadline": "deadline",
    "has_recruiter_name": "recruiter_name",
    "has_recruiter_contact": "recruiter_contact",
    "has_subrole_categories": "subrole_categories",
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
    "full_time": "Permanent Full-time",
    "part_time": "Permanent Part-time",
    "contract": "Contract",
    "contract_full_time": "Contract Full-Time",
    "contract_part_time": "Contract Part-Time",
    "internship": "Internship Full-time",
    "internship_part_time": "Internship Part-time",
    "co_op": "Co-op Full-time",
    "co_op_part_time": "Co-op Part-time",
    "temporary": "Temporary",
    "freelance": "Freelance",
    "unknown": "Unknown",
}

# Fixed high-level role bucket (Excel Role_Category). No commas — Excel list DV delimiter.
ROLE_CATEGORY_VALUES: dict[str, str] = {
    "frontend": "Frontend",
    "backend": "Backend",
    "fullstack": "Full-stack",
    "mobile": "Mobile",
    "devops_sre": "DevOps / SRE",
    "cloud_infra": "Cloud / Infrastructure",
    "data_engineering": "Data Engineering",
    "data_analytics": "Data Analytics / BI",
    "ai_ml": "AI / Machine Learning",
    "applied_ai": "Applied AI",
    "cybersecurity": "Cybersecurity",
    "qa_testing": "QA / Testing",
    "embedded_systems": "Embedded / Systems",
    "game_engines": "Game Engines",
    "it_support": "IT Support / Help Desk",
    "network_telecom": "Network / Telecom",
    "other_tech": "Other tech",
    "non_tech": "Non-tech",
}

# choice key -> (Excel column, LLM schema field, option -> Excel value)
# role_category is classified in a second Jev call after subroles are known (not via derive()).
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
    "has_location_country": _noul(
        "The posting indicates a country (or territory) where this role is based or the office is located.",
        "A country is named (e.g. 'Canada', 'United States', 'UK') or a city/province that clearly identifies one (e.g. 'Toronto, Ontario', 'Berlin, Germany')",
        "No country or identifiable national location; fully remote with no geography, or only a vague region like 'EMEA'",
    ),
    "has_location_city": _noul(
        "The posting states a city, town or metro area for where this role is based or the office is located.",
        "A city or metro is named as the work / office location, e.g. 'Toronto', 'New York, NY', 'London office', 'Bay Area'",
        "No city or metro named; only a country or province, or remote with no office city",
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
    "has_subrole_categories": _noul(
        "Fine-grained technical sub-areas of the role (e.g. React, backend APIs, Kubernetes, SOC, BI dashboards) can be inferred.",
        "The tech stack, responsibilities or title make specific sub-areas clear",
        "The text is too generic to tell what kind of engineering or work it is",
    ),
    "has_position_level": _noul(
        "The seniority level of the role is stated or clearly inferable.",
        "Words like 'Junior', 'Senior', 'Intern', 'Lead', 'Staff', 'entry-level', or a stated years-of-experience requirement",
        "Nothing in the text indicates the level",
    ),
    "role_category": _choice(
        "Pick exactly one high-level role category for this posting. Prefer the single best fit. "
        "Use the posting and any provided subrole_categories list. Use other_tech only when it is clearly technical "
        "but fits none of the other tech buckets. Use non_tech for sales, marketing, HR, finance, pure GTM, etc.",
        {
            "frontend": "UI/client-side web or similar (React, Vue, CSS, browser apps)",
            "backend": "Server-side services/APIs/databases without a primary UI focus",
            "fullstack": "Explicit mix of frontend and backend as one role",
            "mobile": "iOS, Android, React Native, Flutter, or mobile-first apps",
            "devops_sre": "CI/CD, reliability, platform engineering, SRE, release automation",
            "cloud_infra": "Cloud platforms, infra-as-code, networking of cloud resources (AWS/Azure/GCP focus)",
            "data_engineering": "Pipelines, warehouses, ETL/ELT, streaming data platforms",
            "data_analytics": "BI, dashboards, reporting, business/data analysis (not primarily ML research)",
            "ai_ml": "Core ML/AI: model training, research, classical ML, data science modeling, MLOps for training",
            "applied_ai": "Product/engineering roles that apply AI/LLMs (agents, RAG apps, AI features) without primary model research",
            "cybersecurity": "Security engineering, SOC, AppSec, penetration testing, GRC security",
            "qa_testing": "QA, SDET, test automation, quality engineering",
            "embedded_systems": "Firmware, embedded, IoT device software, low-level systems close to hardware",
            "game_engines": "Developing or maintaining game engines as a primary responsibility, including engine systems such as real-time rendering, physics, animation, runtime performance, or engine tooling",
            "it_support": "Help desk, desktop support, IT operations support, service desk",
            "network_telecom": "Network engineering, telecom, connectivity (non-cloud-primary)",
            "other_tech": "Clearly a tech/engineering role that does not fit the buckets above",
            "non_tech": "Non-engineering role (sales, marketing, recruiting, finance, ops without coding focus)",
        },
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
            "full_time": "Permanent full-time employment",
            "part_time": "Permanent part-time employment",
            "contract": "Fixed-term contract, hours not specified",
            "contract_full_time": "Fixed-term contract, full-time hours",
            "contract_part_time": "Fixed-term contract, part-time hours",
            "internship": "Internship, full-time hours",
            "internship_part_time": "Internship, part-time hours",
            "co_op": "Co-op or work term for students, full-time hours",
            "co_op_part_time": "Co-op or work term for students, part-time hours",
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
