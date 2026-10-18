# Repository for "The potential of large language models for the assessment of cognitive engagement in informal online communities"

Associated GitHub repository for the RPTEL article "The potential of large language models for the assessment of cognitive engagement in informal online communities" ([doi: 10.58459/rptel.2027.22034](https://doi.org/10.58459/rptel.2027.22034)).

This tool automates the classification of discussion forum comments using the ICAP framework (Interactive, Constructive, Active, Passive). It sends comments to LLMs with structured prompts, collects multiple responses via majority voting, and stores results back in MongoDB.

## Repository Structure

```
.
├── README.md
├── code/
│   ├── main.py
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── utils/
│       ├── __init__.py
│       ├── funcs.py
│       └── annotations.py
└── supplementary_material/
    ├── supplementary_material_1.pdf
    └── supplementary_material_2.pdf
```

## ICAP Categories

Comments are classified into the following categories:

- **Off-topic** — irrelevant to the project's scientific content or discussion
- **Active (Attention/Engagement)** — general engagement without paraphrasing or repetition
- **Active (Paraphrase/Repeat)** — paraphrasing, repeating, or using hashtags/technical terms
- **Constructive (Idea)** — introducing new ideas or external content
- **Constructive (Elaboration/Reasoning)** — reasoning, elaborating, or establishing cause and effect
- **Interactive** — constructive engagement that references another user's contributions

## Requirements

- Docker and Docker Compose
- A MongoDB instance with the required collections (see below)
- API key(s) for at least one supported LLM provider

### Supported Providers

| Provider       | Environment Variable       | Base URL                                  |
|----------------|----------------------------|-------------------------------------------|
| DeepInfra      | `API_KEY_DEEPINFRA`        | `https://api.deepinfra.com/v1/openai`     |
| OpenAI         | `API_KEY_OPENAI`           | OpenAI default                            |
| Anthropic      | `API_KEY_ANTHROPIC`        | Anthropic default                         |
| Together       | `API_KEY_TOGETHER`         | Together default                          |
| AcademicCloud  | `API_KEY_ACADEMICCLOUD`    | `https://chat-ai.academiccloud.de/v1`     |
| DeepSeek       | `API_KEY_DEEPSEEK`         | `https://api.deepseek.com`                |

## Database Schema

The tool expects a MongoDB database with the following collections:

### `Comments`

Each document represents a comment to be classified.

| Field           | Type     | Description                                      |
|-----------------|----------|--------------------------------------------------|
| `id`            | string   | Unique comment identifier                        |
| `project_title` | string   | Name of the project/forum the comment belongs to  |
| `created_at`    | datetime | Comment creation timestamp                       |
| `context`       | object   | Thread context (see below)                       |

The `context` object contains thread structure information. Fields differ between citizen science platforms (e.g., Zooniverse) and Reddit:

**Citizen science projects:**

| Field               | Description                        |
|----------------------|------------------------------------|
| `id_com`             | Comment ID                         |
| `body_com`           | Comment text                       |
| `user_login_com`     | Comment author                     |
| `id_th_str`          | Thread starter ID                  |
| `body_th_str`        | Thread starter text                |
| `user_login_th_str`  | Thread starter author              |
| `id_pr_com`          | Parent comment ID                  |
| `body_pr_com`        | Parent comment text                |
| `user_login_pr_com`  | Parent comment author              |
| `reply_str_com`      | Reply indicator string             |

**Reddit (`r/askastronomy`):**

| Field               | Description                        |
|----------------------|------------------------------------|
| `id`                 | Comment ID                         |
| `body`               | Comment text                       |
| `author`             | Comment author                     |
| `parent_id`          | Parent comment/post ID             |
| `link_id`            | Thread (submission) ID             |
| `submission_body`    | Submission text                    |
| `submission_author`  | Submission author                  |
| `parent_body`        | Parent comment text                |
| `parent_author`      | Parent comment author              |
| `reply_sentence`     | Reply indicator string             |

### `Projects`

Each document describes a project/forum and its classification examples.

| Field           | Type     | Description                                        |
|-----------------|----------|----------------------------------------------------|
| `title`         | string   | Project name (must match `project_title` in Comments) |
| `description`   | string   | Project description                                |
| `introduction`  | string   | Project introduction text                          |
| `examples_new`  | object   | Few-shot examples per ICAP category (see below)    |

The `examples_new` field maps each ICAP category to a list of example objects. Each example has `Thread Starter`, `Previous Comment` (or `Parent Comment` for Reddit), `Target Comment`, and `Rationale` fields:

```json
{
  "Off-topic": [
    {
      "Thread Starter": "...",
      "Previous Comment": "...",
      "Target Comment": "...",
      "Rationale": "..."
    }
  ],
  "Active (Attention/Engagement)": [...],
  "Active (Paraphrase/Repeat)": [...],
  "Constructive (Idea)": [...],
  "Constructive (Elaboration/Reasoning)": [...],
  "Interactive": [...]
}
```

Each category should have at least 2 examples.

### `annotations` (optional)

Used by `utils/annotations.py` to select comments that have been annotated by specific annotators (for validation against human labels). Not required for general classification.

## Configuration

All configuration is done through environment variables in `code/docker-compose.yml`:

| Variable         | Description                                                                 |
|------------------|-----------------------------------------------------------------------------|
| `DATABASE_URL`   | MongoDB connection string                                                   |
| `DATABASE`       | MongoDB database name                                                       |
| `PROVIDER`       | LLM provider (`deepinfra`, `openai`, `anthropic`, `together`, `academiccloud`, `deepseek`) |
| `MODELS`         | JSON array of model identifiers, e.g. `'["meta-llama/Meta-Llama-3.1-8B-Instruct"]'` |
| `PROJECTS`       | JSON array of project names (currently unused; edit `main.py` directly)     |
| `API_KEY_*`      | API key for the chosen provider                                             |
| `SEMAPHORE`      | Maximum number of concurrent API calls (e.g. `200`)                         |

## Prompt Configuration

The tool supports prompt ablation experiments through `PromptConfig`. Each configuration controls:

- `include_examples` — whether to include few-shot examples in the prompt
- `include_rules` — whether to include the ICAP classification rules
- `order` — ordering of prompt sections when both examples and rules are included (1, 2, or 3)

Uncomment additional configurations in `code/main.py` to run ablation experiments with different prompt variants.

## Usage

1. Set up your MongoDB with the required collections and data.

2. Edit `code/docker-compose.yml` with your database URL, API keys, desired models, and provider.

3. Edit `code/main.py` to specify which comments to classify. The default configuration selects comments by project and date range. Adapt the `projects_dates` dictionary and the MongoDB query filter to your needs.

4. Build and run:

```bash
cd code
docker compose up --build
```

## Supplementary Material

The `supplementary_material/` folder contains additional resources accompanying the article:

- **supplementary_material_1.pdf**
- **supplementary_material_2.pdf**

## Results

Classification results are stored back in the `Comments` collection under `results_revision.<model_name>.<config_key>`, where `<model_name>` is the model identifier with dots removed, and `<config_key>` encodes the prompt configuration (e.g., `ex1_ru1_o1` for examples=True, rules=True, order=1).

Each result contains:

```json
{
  "label": "Interactive",
  "prompt": "...",
  "additional_tries": 0,
  "votes": [
    {
      "answer": {
        "label": "Interactive",
        "explanation": "...",
        "thought_process": "..."
      },
      "info": {
        "completion_tokens": 150,
        "prompt_tokens": 1200,
        "total_tokens": 1350
      }
    }
  ],
  "config": {
    "include_examples": true,
    "include_rules": true,
    "order": 1
  }
}
```

The majority vote across 5 calls (with up to 5 additional tie-breaking calls) determines the final label.
