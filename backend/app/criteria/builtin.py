"""Built-in criteria — the standard filters found on mainstream job boards
(skills, experience, location, education, certs, visa, salary, availability),
seeded into the global library. Each carries a field_type so the Job
Descriptions page can render the right control (text box, number, dropdown,
toggle) when a recruiter selects it for a specific job — see JobCriterion.
The LLM scoring prompt takes the active per-job selections as scoring context.

default_enabled/default_value are used only when a new job is created (see
criteria/service.py seed_default_job_criteria) to pre-populate a sensible
starting selection, so the criteria checklist isn't empty on first view —
they're not columns on Criterion itself."""

BUILTIN_CRITERIA = [
    {
        "name": "Skills match",
        "description": "Overlap between resume skills and JD required/preferred skills.",
        "weight": 1.0,
        "field_type": "text",
        "options": [],
        "default_enabled": True,
        "default_value": "",
    },
    {
        "name": "Minimum years of experience",
        "description": "Total relevant experience required.",
        "weight": 1.0,
        "field_type": "number",
        "options": [],
        "default_enabled": True,
        "default_value": "0",
    },
    {
        "name": "Location / remote fit",
        "description": "Candidate location vs. job location or remote policy.",
        "weight": 0.6,
        "field_type": "select",
        "options": ["Onsite", "Hybrid", "Remote", "Any"],
        "default_enabled": True,
        "default_value": "Any",
    },
    {
        "name": "Minimum education level",
        "description": "Degree level required.",
        "weight": 0.5,
        "field_type": "select",
        "options": ["High school", "Associate's", "Bachelor's", "Master's", "PhD", "Any"],
        "default_enabled": False,
        "default_value": "Any",
    },
    {
        "name": "Certifications",
        "description": "Relevant certifications required.",
        "weight": 0.4,
        "field_type": "text",
        "options": [],
        "default_enabled": False,
        "default_value": "",
    },
    {
        "name": "Work visa sponsorship",
        "description": "Whether this role can sponsor a work visa.",
        "weight": 0.8,
        "field_type": "select",
        "options": ["Sponsorship available", "No sponsorship", "Case-by-case", "Any"],
        "default_enabled": True,
        "default_value": "Any",
    },
    {
        "name": "Salary budget (max, USD)",
        "description": "Upper bound of the compensation range for this role.",
        "weight": 0.5,
        "field_type": "number",
        "options": [],
        "default_enabled": False,
        "default_value": "",
    },
    {
        "name": "Requires immediate availability",
        "description": "Candidate must be able to start within 2 weeks.",
        "weight": 0.4,
        "field_type": "boolean",
        "options": [],
        "default_enabled": False,
        "default_value": "false",
    },
]

CRITERION_FIELDS = ("name", "description", "weight", "field_type", "options")
