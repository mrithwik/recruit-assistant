"""Tech-role persona pools for the synthetic Gmail load-test dataset (see
architecture/project-log.md for context). Reuses the generic name/school/visa
pools and writing-style personas from dev_tools/sample_data_generator.py
(don't duplicate those) but defines its own tech-specific role/skill/cert
pools, since that generator's DOMAINS are broad-workforce, not the specific
tech-role mix (SWE variants, AI Engineer, AI FDE, PM/PO/BA) asked for here.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime

from app.dev_tools.sample_data_generator import (
    CITIES,
    DEGREES,
    EMPLOYMENT_WEIGHTS,
    FIRST_NAMES,
    LAST_NAMES,
    PERSONAS as WRITING_STYLES,
    SCHOOLS,
    VISA_WEIGHTS,
    random_date_in_bucket,
    weighted_choice,
)

# Interaction/temperament personas — how a candidate behaves across a
# multi-email relationship, distinct from WRITING_STYLES (which governs
# prose register). Deliberately includes difficult ones per the explicit
# request to stress-test the pipeline with challenging back-and-forth mail.
CHALLENGE_PERSONAS = [
    "patient", "laid_back", "neutral", "anxious", "worried", "tense",
    "micromanaging", "pushy", "demanding",
]

# --------------------------------------------------------------------------
# Tech-role pools — current (2026) market roles and stacks
# --------------------------------------------------------------------------

ROLE_SKILLS: dict[str, list[str]] = {
    "swe_backend": ["Python", "FastAPI", "Django", "Go", "Java", "Spring Boot",
                    "PostgreSQL", "Redis", "Kubernetes", "Docker", "gRPC", "Kafka"],
    "swe_frontend": ["TypeScript", "React", "Next.js", "Vue", "Svelte", "Tailwind CSS",
                      "GraphQL", "Vite", "Web Accessibility", "Playwright"],
    "swe_fullstack": ["TypeScript", "React", "Node.js", "Python", "PostgreSQL",
                       "Next.js", "tRPC", "Docker", "AWS"],
    "swe_mobile": ["Swift", "SwiftUI", "Kotlin", "Jetpack Compose", "React Native",
                   "Flutter", "Firebase", "CI/CD for mobile"],
    "swe_data_platform": ["Python", "SQL", "Spark", "Airflow", "dbt", "Snowflake",
                           "Kafka", "Terraform", "AWS Redshift"],
    "swe_embedded": ["C", "C++", "Rust", "RTOS", "FreeRTOS", "embedded Linux",
                      "I2C/SPI", "hardware bring-up"],
    "devops_sre": ["Kubernetes", "Terraform", "AWS", "GCP", "Prometheus", "Grafana",
                    "Helm", "Ansible", "CI/CD pipelines", "incident response"],
    "security_engineer": ["threat modeling", "SIEM", "penetration testing", "AWS IAM",
                           "SOC2", "vulnerability management", "Python", "Zero Trust"],
    "qa_engineer": ["Playwright", "Selenium", "pytest", "test automation frameworks",
                     "CI/CD", "API testing", "load testing (k6/Locust)"],
    "data_scientist": ["Python", "pandas", "scikit-learn", "PyTorch", "SQL",
                        "experimentation/A-B testing", "statistics", "Jupyter"],
    "ml_engineer": ["PyTorch", "TensorFlow", "MLflow", "Kubeflow", "model serving",
                     "feature stores", "distributed training", "Python"],
    "ai_engineer": ["LLM APIs (OpenAI/Anthropic)", "LangChain", "LlamaIndex", "RAG pipelines",
                     "vector databases (Pinecone/Weaviate/pgvector)", "prompt engineering",
                     "Python", "evaluation harnesses", "fine-tuning"],
    "ai_fde": ["LLM APIs (OpenAI/Anthropic)", "LangChain", "RAG pipelines", "Python",
               "customer-facing solutioning", "rapid prototyping", "vector databases",
               "internal tooling", "stakeholder demos"],
    "cloud_platform_engineer": ["AWS", "GCP", "Azure", "Terraform", "Kubernetes",
                                 "internal developer platforms", "cost optimization"],
    "product_owner": ["backlog grooming", "user story writing", "Scrum", "Jira",
                       "stakeholder alignment", "acceptance criteria", "roadmapping"],
    "product_manager": ["product strategy", "roadmapping", "user research", "SQL",
                         "A/B testing", "go-to-market", "stakeholder management", "Jira"],
    "business_analyst": ["requirements gathering", "process mapping", "SQL",
                          "stakeholder interviews", "BRDs", "Tableau/Power BI", "Agile"],
    "project_manager": ["Agile/Scrum", "PMP methodology", "risk management",
                         "cross-functional coordination", "Jira", "budget tracking", "Gantt planning"],
}

ROLE_TITLES: dict[str, list[str]] = {
    "swe_backend": ["Backend Engineer", "Software Engineer, Backend", "Platform Engineer"],
    "swe_frontend": ["Frontend Engineer", "UI Engineer", "Software Engineer, Frontend"],
    "swe_fullstack": ["Full-Stack Engineer", "Software Engineer"],
    "swe_mobile": ["Mobile Engineer", "iOS Engineer", "Android Engineer"],
    "swe_data_platform": ["Data Platform Engineer", "Data Engineer"],
    "swe_embedded": ["Embedded Software Engineer", "Firmware Engineer"],
    "devops_sre": ["DevOps Engineer", "Site Reliability Engineer", "Platform Engineer"],
    "security_engineer": ["Security Engineer", "Application Security Engineer"],
    "qa_engineer": ["QA Engineer", "Software Development Engineer in Test"],
    "data_scientist": ["Data Scientist", "Applied Scientist"],
    "ml_engineer": ["Machine Learning Engineer", "ML Platform Engineer"],
    "ai_engineer": ["AI Engineer", "Applied AI Engineer", "GenAI Engineer"],
    "ai_fde": ["AI Forward Deployed Engineer", "Forward Deployed Engineer"],
    "cloud_platform_engineer": ["Cloud Platform Engineer", "Infrastructure Engineer"],
    "product_owner": ["Product Owner", "Associate Product Owner"],
    "product_manager": ["Product Manager", "Senior Product Manager"],
    "business_analyst": ["Business Analyst", "Senior Business Analyst"],
    "project_manager": ["Project Manager", "Technical Program Manager"],
}

SENIORITIES = ["Junior", "Mid-Level", "Senior", "Staff", "Principal"]
SENIORITY_YEARS = {"Junior": (0, 2), "Mid-Level": (2, 5), "Senior": (5, 9), "Staff": (9, 14), "Principal": (12, 20)}

CERTS: dict[str, list[str]] = {
    "swe_backend": ["AWS Certified Solutions Architect", "CKA (Certified Kubernetes Administrator)"],
    "swe_frontend": [],
    "swe_fullstack": ["AWS Certified Developer"],
    "swe_mobile": ["Apple Certified iOS Developer"],
    "swe_data_platform": ["AWS Certified Data Analytics"],
    "swe_embedded": [],
    "devops_sre": ["CKA (Certified Kubernetes Administrator)", "AWS Certified DevOps Engineer", "HashiCorp Terraform Associate"],
    "security_engineer": ["CISSP", "OSCP", "Security+"],
    "qa_engineer": ["ISTQB Certified Tester"],
    "data_scientist": ["AWS Certified Machine Learning Specialty"],
    "ml_engineer": ["AWS Certified Machine Learning Specialty", "TensorFlow Developer Certificate"],
    "ai_engineer": ["DeepLearning.AI LLM Specialization"],
    "ai_fde": [],
    "cloud_platform_engineer": ["AWS Certified Solutions Architect Professional", "Google Cloud Professional Architect"],
    "product_owner": ["Certified Scrum Product Owner (CSPO)"],
    "product_manager": ["Pragmatic Institute PMC", "Certified Scrum Product Owner (CSPO)"],
    "business_analyst": ["CBAP (Certified Business Analysis Professional)"],
    "project_manager": ["PMP (Project Management Professional)", "Certified ScrumMaster (CSM)"],
}

ROLES = list(ROLE_SKILLS.keys())


@dataclass
class Persona:
    idx: int
    first_name: str
    last_name: str
    email: str
    phone: str
    role: str
    title: str
    seniority: str
    years_exp: int
    skills: list[str]
    certs: list[str]
    company_history: list[str]
    school: str
    degree: str
    city: str
    employment_status: str
    visa_status: str
    writing_style: str
    challenge_persona: str
    include_cover_letter: bool
    include_work_auth: bool
    include_photo_id: bool
    include_passport: bool
    ocr_image_resume: bool
    has_followups: bool
    has_resume_update: bool
    has_casual_checkins: bool
    is_back_and_forth: bool
    submitted_at: datetime = field(default_factory=datetime.utcnow)


_COMPANIES = [
    "Acme Corp", "Widget Labs", "Northwind Software", "Globex", "Initech",
    "Vertex Systems", "Bluepeak", "Cascade Digital", "Ironleaf", "Nimbus Cloud",
    "Redwood Analytics", "Fathom AI", "Harbor Robotics", "Lumen Health",
    "Orbit Logistics", "Pinecrest Media", "Quartz Financial", "Sable Studio",
    "Tidewater Retail", "Vantage Point", "Anchorpoint", "Brightline",
]


def generate_personas(count: int, seed: int, ocr_count: int) -> list[Persona]:
    rng = random.Random(seed)
    ocr_indices = set(rng.sample(range(count), k=min(ocr_count, count)))
    personas: list[Persona] = []
    now = datetime.utcnow()

    for i in range(count):
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        role = rng.choice(ROLES)
        seniority = rng.choice(SENIORITIES)
        lo, hi = SENIORITY_YEARS[seniority]
        years_exp = rng.randint(lo, hi)
        skills_pool = ROLE_SKILLS[role]
        skills = rng.sample(skills_pool, k=min(len(skills_pool), rng.randint(4, len(skills_pool))))
        certs_pool = CERTS.get(role, [])
        certs = rng.sample(certs_pool, k=min(len(certs_pool), rng.randint(0, len(certs_pool))))
        n_companies = 1 if years_exp < 2 else rng.randint(1, min(4, 1 + years_exp // 3))
        company_history = rng.sample(_COMPANIES, k=min(len(_COMPANIES), n_companies))
        _, submitted_at = random_date_in_bucket(rng, now)

        personas.append(
            Persona(
                idx=i,
                first_name=first,
                last_name=last,
                email=f"{first.lower()}.{last.lower()}{rng.randint(1, 999)}@example.com",
                phone=f"({rng.randint(200, 989)}) {rng.randint(200, 989)}-{rng.randint(1000, 9999)}",
                role=role,
                title=rng.choice(ROLE_TITLES[role]),
                seniority=seniority,
                years_exp=years_exp,
                skills=skills,
                certs=certs,
                company_history=company_history,
                school=rng.choice(SCHOOLS),
                degree=rng.choice(DEGREES),
                city=rng.choice(CITIES),
                employment_status=weighted_choice(rng, EMPLOYMENT_WEIGHTS),
                visa_status=weighted_choice(rng, VISA_WEIGHTS),
                writing_style=rng.choice(WRITING_STYLES),
                challenge_persona=rng.choice(CHALLENGE_PERSONAS),
                include_cover_letter=rng.random() < 0.4,
                include_work_auth=rng.random() < 0.3,
                include_photo_id=rng.random() < 0.15,
                include_passport=rng.random() < 0.1,
                ocr_image_resume=i in ocr_indices,
                has_followups=rng.random() < 0.35,
                has_resume_update=rng.random() < 0.15,
                has_casual_checkins=rng.random() < 0.12,
                is_back_and_forth=rng.random() < 0.10,
                submitted_at=submitted_at,
            )
        )
    return personas
