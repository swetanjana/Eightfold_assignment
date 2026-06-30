"""
Skill name canonicalization.

Different sources represent the same skill in different ways:
    - "ML", "machine learning", "Machine-Learning" → "Machine Learning"
    - "JS", "javascript", "JavaScript" → "JavaScript"
    - "Python3", "python 3", "Python" → "Python"

This module maps raw skill strings to a single canonical form using
a local alias dictionary.  The dictionary is intentionally curated
rather than AI-generated — it covers the most common tech skills
seen in engineering resumes.

Skills not found in the dictionary are title-cased and returned as-is,
so the system degrades gracefully for unknown skills rather than
dropping them.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical skill alias dictionary
# ---------------------------------------------------------------------------

# Each key is a lowercase alias; the value is the canonical form.
# This is the single source of truth for skill name standardization.
_SKILL_ALIASES: dict[str, str] = {
    # Programming Languages
    "python": "Python",
    "python3": "Python",
    "python 3": "Python",
    "py": "Python",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "node": "Node.js",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "java": "Java",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "csharp": "C#",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "ruby": "Ruby",
    "swift": "Swift",
    "kotlin": "Kotlin",
    "r": "R",
    "scala": "Scala",
    "php": "PHP",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",

    # AI / ML
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "machine-learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "dl": "Deep Learning",
    "deep-learning": "Deep Learning",
    "artificial intelligence": "Artificial Intelligence",
    "ai": "Artificial Intelligence",
    "natural language processing": "NLP",
    "nlp": "NLP",
    "computer vision": "Computer Vision",
    "cv": "Computer Vision",
    "reinforcement learning": "Reinforcement Learning",
    "rl": "Reinforcement Learning",
    "generative ai": "Generative AI",
    "gen ai": "Generative AI",
    "llm": "LLM",
    "large language models": "LLM",

    # ML Frameworks
    "tensorflow": "TensorFlow",
    "tf": "TensorFlow",
    "pytorch": "PyTorch",
    "torch": "PyTorch",
    "keras": "Keras",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scipy": "SciPy",

    # Web Frameworks
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "react js": "React",
    "angular": "Angular",
    "angularjs": "Angular",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "express": "Express.js",
    "expressjs": "Express.js",
    "spring": "Spring",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",

    # Databases
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "dynamodb": "DynamoDB",
    "cassandra": "Cassandra",
    "sqlite": "SQLite",

    # Cloud & DevOps
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "GCP",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
    "azure": "Azure",
    "microsoft azure": "Azure",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "terraform": "Terraform",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "jenkins": "Jenkins",
    "github actions": "GitHub Actions",
    "git": "Git",

    # Data Engineering
    "apache spark": "Apache Spark",
    "spark": "Apache Spark",
    "pyspark": "PySpark",
    "kafka": "Apache Kafka",
    "apache kafka": "Apache Kafka",
    "airflow": "Apache Airflow",
    "apache airflow": "Apache Airflow",
    "data pipelines": "Data Pipelines",
    "etl": "ETL",

    # Protocols & Tools
    "rest": "REST",
    "rest api": "REST",
    "restful": "REST",
    "graphql": "GraphQL",
    "grpc": "gRPC",
    "microservices": "Microservices",
    "linux": "Linux",
    "unix": "Unix",
    "agile": "Agile",
    "scrum": "Scrum",
}


def normalize_skill(raw: str | None) -> Optional[str]:
    """Normalize a single raw skill string to its canonical form.

    Args:
        raw: The raw skill string from any source.

    Returns:
        The canonical skill name, or the title-cased original if
        no alias is found.  ``None`` if the input is empty.

    Examples:
        >>> normalize_skill("ML")
        'Machine Learning'
        >>> normalize_skill("reactjs")
        'React'
        >>> normalize_skill("Python3")
        'Python'
        >>> normalize_skill("some-unknown-skill")
        'Some-Unknown-Skill'
        >>> normalize_skill("")
        None
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip()
    if not cleaned:
        return None

    lookup_key = cleaned.lower()
    canonical = _SKILL_ALIASES.get(lookup_key)

    if canonical:
        return canonical

    # Unknown skill — return title-cased form rather than dropping it.
    # This ensures we never lose data; we just can't canonicalize it.
    logger.debug("Unknown skill alias %r — using title-cased form", raw)
    return cleaned.title()


def normalize_skills(raw_list: list[str]) -> list[str]:
    """Normalize a list of raw skill strings, deduplicating canonical forms.

    Args:
        raw_list: List of raw skill strings from any source.

    Returns:
        Deduplicated list of canonical skill names.
        Order is preserved (first occurrence kept).

    Examples:
        >>> normalize_skills(["Python", "ML", "python3", "Machine Learning"])
        ['Python', 'Machine Learning']
    """
    seen: set[str] = set()
    result: list[str] = []

    for raw in raw_list:
        canonical = normalize_skill(raw)
        if canonical and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)

    return result
