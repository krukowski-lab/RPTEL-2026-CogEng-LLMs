import os, json
from utils import annotations, funcs
from utils.funcs import PromptConfig
from pymongo import MongoClient
import asyncio
from datetime import datetime


def main():
    connection_string = os.getenv("DATABASE_URL")
    db_client = MongoClient(connection_string)
    db = db_client[os.getenv("DATABASE")]

    desired_models = os.getenv('MODELS', '[]')
    desired_models = json.loads(desired_models)

    # Fetch comment IDs per project.
    # Alternatively, use annotations.get_relevant_ids(db) to select
    # comments that have been annotated by both annotators.
    rel_comment_ids = {}
    projects_dates = {
        "r/askastronomy": ("2021-01-01", "2022-01-01"),
        "Exoplanet Explorers": ("2018-01-01", "2019-01-01"),
        "Galaxy Zoo": ("2021-01-01", "2022-01-01"),
    }
    for project, (start_str, end_str) in projects_dates.items():
        start_date = datetime.strptime(start_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_str, "%Y-%m-%d")
        rel_comment_ids[project] = [
            comment['id'] for comment in db.Comments.find(
                {
                    "$and": [
                        {"project_title": project},
                        {"created_at": {"$gte": start_date, "$lt": end_date}},
                        {f'results_final.{"Qwen/QwQ-32B".replace(".", "")}': {"$exists": False}}
                    ]
                },
                {"_id": 0, "id": 1}
            )
        ]
        print(f"fetched comments for project {project} have length {len(rel_comment_ids[project])}")

    client = funcs.createClient(os.getenv("PROVIDER"))

    # Prompt ablation configurations.
    # Uncomment additional configs to run ablation experiments
    # with different combinations of examples, rules, and orderings.
    configs = [
        PromptConfig(include_examples=True, include_rules=True, order=1),
        #PromptConfig(include_examples=True, include_rules=True, order=2),
        #PromptConfig(include_examples=True, include_rules=True, order=3),
        #PromptConfig(include_examples=True, include_rules=False),
        #PromptConfig(include_examples=False, include_rules=True),
        #PromptConfig(include_examples=False, include_rules=False),
    ]

    for model in desired_models:
        for config in configs:
            print(f"Running {model} with config {config.key}")
            asyncio.run(funcs.createLabels_async(db, rel_comment_ids, client, model, config))

if __name__ == "__main__":
    main()
