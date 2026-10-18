import anthropic
from openai import OpenAI
from openai.types import CompletionUsage
from openai import APIError, APIConnectionError, RateLimitError, UnprocessableEntityError
from together import Together
import re, json, os
from pydantic import BaseModel, field_validator, ValidationError, model_validator
from collections import Counter
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from typing import Optional
from bson import ObjectId
from dataclasses import dataclass, asdict
import asyncio
from functools import partial

@dataclass
class PromptConfig:
    include_examples: bool = True
    include_rules: bool = True
    order: int = 1

    @property
    def key(self) -> str:
        parts = []
        parts.append(f"ex{int(self.include_examples)}")
        parts.append(f"ru{int(self.include_rules)}")
        if self.include_examples and self.include_rules:
            parts.append(f"o{self.order}")
        return "_".join(parts)

def createClient(provider: str):
    client = None
    if provider == "anthropic":
        client = anthropic.Anthropic(
            api_key=os.getenv("API_KEY_ANTHROPIC"),)
    elif provider == "together":
        client = Together(api_key=os.getenv("API_KEY_TOGETHER"))
    elif provider == "deepinfra":
        client = OpenAI(
            api_key=os.getenv("API_KEY_DEEPINFRA"),
            base_url="https://api.deepinfra.com/v1/openai",
        )
    elif provider == "openai":
        client = OpenAI(
            api_key=os.getenv("API_KEY_OPENAI"),
        )
    elif provider == "academiccloud":
        client = OpenAI(
            api_key=os.getenv("API_KEY_ACADEMICCLOUD"),
            base_url="https://chat-ai.academiccloud.de/v1",
        )
    elif provider == "deepseek":
        client = OpenAI(
            api_key=os.getenv("API_KEY_DEEPSEEK"),
            base_url="https://api.deepseek.com")
    return client


def getForumDescription(db, forumname: str) -> str:
    output = None
    entry = db.Projects.find_one({'title': forumname})
    if entry is not None:
        descr = entry['description']
        intro = entry['introduction']
        text = descr + "\n" + intro
        text = re.sub(r'\[.*?\]\(.*?\)', '', text)
        output = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    else:
        print(f"Forum {forumname} is missing. Output None.")
    return output


def validateServerResponse(response, client="openai"):
    if client == "openai":
        if hasattr(response, 'choices'):
            if len(response.choices) > 0:
                return response.choices[0].message.content
        else:
            print("No valid response found.")
            return None

    else:  # Needs to be added for other clients than openai
        return None


def getContextDescription(description: str, reddit=False) -> str:
    prompt = "Summarise the following project description into one sentence that describes what users have to do in the project, making sure that it completes the following sentence: 'You are an expert AI assistant specializing in classifying text comments from online citizen science project discussion forums, where users (...)'. Make sure the summary is about what the users do in the project and discuss in the forum and only give this summary. This is the description: \n" + description
    if reddit:
        prompt = "Summarise the following subreddit description into one sentence that describes what users have to discuss in the project, making sure that it completes the following sentence: 'You are an expert AI assistant specializing in classifying text comments from reddit discussion forums, where users (...)'. Make sure the summary is about what the users discuss in the subreddit and only give this summary. This is the description: \n" + description
    answer = OpenAI(
        api_key=os.getenv("API_KEY_DEEPINFRA"),
        base_url="https://api.deepinfra.com/v1/openai",
    ).beta.chat.completions.parse(
        messages=[
            {"role": "user", "content": prompt},
        ],
        model="meta-llama/Llama-3.3-70B-Instruct",
        temperature=0
    )
    answer = validateServerResponse(answer)
    return answer

def getContextInfo(context: dict, key: str, reddit=False) -> str:
    """Extracts and formats a context field based on the comment's position in its thread."""
    if reddit:
        thread_starter = False
        second_comment = False

        thing_id = context.get("id")
        parent_id = context.get("parent_id")
        link_id = context.get("link_id")

        if f"t3_{thing_id}" == link_id:
            thread_starter = True
        elif parent_id == link_id:
            second_comment = True

        if thread_starter:
            if key == "submission_author":
                return ""
            elif key == "submission_body":
                return "Target comment is thread starter"
            elif key == "parent_body":
                return "N/A"
            elif key == "parent_author":
                return ""
            elif key == 'author':
                return f"(@{context.get(key, "")})"
            elif key == "body":
                return f'"{context.get(key, "")}"'
            elif key == "reply_sentence":
                return ""
            else:
                return context.get(key, "")
        elif second_comment:
            if key == "parent_author":
                return ""
            elif key == "parent_body":
                return "Parent comment is thread starter"
            elif key == "submission_author":
                return f"(@{context.get(key, "")})"
            elif key == "submission_body":
                return f'"{context.get(key, "")}"'
            elif key == 'author':
                return f"(@{context.get(key, "")})"
            elif key == "body":
                return f'"{context.get(key, "")}"'
            else:
                return context.get(key, "")
        else:
            if key in ['parent_author', 'submission_author', 'author']:
                return f"(@{context.get(key, "")})"
            elif key == "reply_sentence":
                return context.get(key, "")
            else:
                return f'"{context.get(key, "")}"'
    else:
        thread_starter = False
        second_comment = False

        if context.get("id_th_str") == context.get("id_com"):
            thread_starter = True
        elif context.get("id_th_str") == context.get("id_pr_com"):
            second_comment = True

        if thread_starter:
            if key == "user_login_th_str":
                return ""
            elif key == "body_th_str":
                return "Target comment is thread starter"
            elif key == "body_pr_com":
                return "N/A"
            elif key == "user_login_pr_com":
                return ""
            elif key == 'user_login_com':
                return f"(@{context.get(key, "")})"
            elif key == "body_com":
                return f'"{context.get(key, "")}"'
            elif key == "reply_str_com":
                return ""
            else:
                return context.get(key, "")
        elif second_comment:
            if key == "user_login_pr_com":
                return ""
            elif key == "body_pr_com":
                return "Parent comment is thread starter"
            elif key == "user_login_th_str":
                return f"(@{context.get(key, "")})"
            elif key == "body_th_str":
                return f'"{context.get(key, "")}"'
            elif key == 'user_login_com':
                return f"(@{context.get(key, "")})"
            elif key == "body_com":
                return f'"{context.get(key, "")}"'
            else:
                return context.get(key, "")
        else:
            if key in ['user_login_pr_com', 'user_login_th_str', 'user_login_com']:
                return f"(@{context.get(key, "")})"
            elif key == "reply_str_com":
                return context.get(key, "")
            else:
                return f'"{context.get(key, "")}"'


def formatExample(label: str, example: dict, reddit=False) -> str:
    thread = example.get("Thread Starter")
    prev = example.get("Previous Comment")
    target = example.get("Target Comment")
    rationale = example.get("Rationale")

    if reddit:
        output = f'Thread: {thread} → Parent: {prev} → Target: {target}\nLabel: {label} ({rationale}\n)'
    else:
        output = f'Thread: {thread} → Previous: {prev} → Target: {target}\nLabel: {label} ({rationale}\n)'

    return output

def createUserPrompt(context: dict,
                     forumname: str,
                     project_context: str,
                     examples: dict,
                     config: PromptConfig) -> str:
    if context is None:
        print("THERE IS AN ISSUE IN createUserPrompt()!!")
    if forumname == "r/askastronomy":
        platform_specific_project_name = "subreddit"
        reddit = True
    else:
        platform_specific_project_name = "project"
        reddit = False
    task = f"""Your task is to classify the Target Comment using the ICAP framework categories below."""
    thread_context = f"""**CONTEXT:**
Thread Starter {getContextInfo(context, "user_login_th_str") if not reddit else getContextInfo(context, "submission_author", reddit=True)}: {getContextInfo(context, "body_th_str") if not reddit else getContextInfo(context, "submission_body", reddit=True)}
{"Previous" if not reddit else "Parent"} Comment {getContextInfo(context, "user_login_pr_com") if not reddit else getContextInfo(context, "parent_author", reddit=True)}: {getContextInfo(context, "body_pr_com") if not reddit else getContextInfo(context, "parent_body", reddit=True)}
Target Comment {getContextInfo(context, "user_login_com") if not reddit else getContextInfo(context, "author", reddit=True)} {getContextInfo(context, "reply_str_com") if not reddit else getContextInfo(context, "reply_sentence", reddit=True)}: {getContextInfo(context, "body_com") if not reddit else getContextInfo(context, "body", reddit=True)}"""

    icap_rules = """**CLASSIFICATION RULES (apply in order):**
1. Off-topic: If a comment lacks content relevance and is irrelevant to the project's scientific content or discussion, label it as Off-topic.
2. Active: If the comment is on-topic, check if it involves paraphrasing, repeating, or using hashtags or technical terms. If so, label it as Active (Paraphrase/Repeat), even when it contains a single hashtag or technical term without further explanation. If the comment simply shows general engagement with project content by seeking information, but without specific paraphrasing or repetition of the discussion's content, label it as Active (Attention/Engagement).
3. Constructive: If the comment is not classified as Active, determine whether it involves constructive behavior. If the user is reasoning, elaborating, explaining or establishing a cause and effect relationship, label it as Constructive (Elaboration/Reasoning). If the user rather introduces a new idea or external content, label it as Constructive (Idea). The latter particularly applies when the comment is the thread starter and contains new ideas, hashtags or technical terms to introduce a topic. Simple questions without the introduction of new content don't qualify here. 
4. Interactive: For a comment to be labeled as Interactive, it must be both Constructive and contain references to another user. References include phrases like "I agree with you", "your point makes sense", or other engagement with another user's contributions, which can be explicit (e.g. through a reply or mention) or implicit. Interactive comments reflect a constructive dialogue, where the user builds on, challenges or responds to another user's ideas.

Use this guide to systematically evaluate and label each comment based on the observed cognitive engagement, explaining your answer."""

    icap_examples = f"""Consider the following examples for reference:

**CATEGORY EXAMPLES:**
**0. Off-topic**
Example 1: {formatExample(label="Off-topic",example=examples.get("Off-topic")[0])}
Example 2: {formatExample(label="Off-topic",example=examples.get("Off-topic")[1])}
**1. Active (Attention/Engagement)**
Example 1: {formatExample(label="Active (Attention/Engagement)",example=examples.get("Active (Attention/Engagement)")[0])}
Example 2: {formatExample(label="Active (Attention/Engagement)",example=examples.get("Active (Attention/Engagement)")[1])}
**2. Active (Paraphrase/Repeat)**
Example 1: {formatExample(label="Active (Paraphrase/Repeat)",example=examples.get("Active (Paraphrase/Repeat)")[0])}
Example 2: {formatExample(label="Active (Paraphrase/Repeat)",example=examples.get("Active (Paraphrase/Repeat)")[1])}
**3. Constructive (Idea)**
Example 1: {formatExample(label="Constructive (Idea)",example=examples.get("Constructive (Idea)")[0])}
Example 2: {formatExample(label="Constructive (Idea)",example=examples.get("Constructive (Idea)")[1])}
**4. Constructive (Elaboration/Reasoning)**
Example 1: {formatExample(label="Constructive (Elaboration/Reasoning)",example=examples.get("Constructive (Elaboration/Reasoning)")[0])}
Example 2: {formatExample(label="Constructive (Elaboration/Reasoning)",example=examples.get("Constructive (Elaboration/Reasoning)")[1])}
**5. Interactive**
Example 1: {formatExample(label="Interactive",example=examples.get("Interactive")[0])}
Example 2: {formatExample(label="Interactive",example=examples.get("Interactive")[1])}
"""
    output_format = """
**OUTPUT FORMAT:**
```json
{
  "label": "EXACT_LABEL_NAME",
  "explanation": "Brief reasoning: why this label fits and others don't"
}
```
    """
    parts = [project_context, task]

    if config.include_examples and config.include_rules:
        orderings = {
            1: [thread_context, icap_rules, icap_examples],
            2: [icap_rules, thread_context, icap_examples],
            3: [icap_rules, icap_examples, thread_context],
        }
        parts += orderings[config.order]
    else:
        parts.append(thread_context)
        if config.include_rules:
            parts.append(icap_rules)
        if config.include_examples:
            parts.append(icap_examples)

    parts.append(output_format)
    return "\n".join(parts)


def streamLineLabel(label: str):
    labels = ["Active (Attention/Engagement)",
              "Active (Paraphrase/Repeat)",
              "Constructive (Idea)",
              "Constructive (Elaboration/Reasoning)",
              "Interactive",
              "Off-topic"]
    if label in labels:
        return label
    elif "attention" in label.lower() or "engagement" in label.lower():
        return "Active (Attention/Engagement)"
    elif "paraphrase" in label.lower() or "repeat" in label.lower():
        return "Active (Paraphrase/Repeat)"
    elif "constructive" in label.lower() or "idea" in label.lower():
        return "Constructive (Idea)"
    elif "elaboration" in label.lower() or "reasoning" in label.lower():
        return "Constructive (Elaboration/Reasoning)"
    elif "interactive" in label.lower():
        return "Interactive"
    elif "off" in label.lower() or "topic" in label.lower():
        return "Off-topic"
    return label


class LLMAnswer(BaseModel):
    label: str
    explanation: str
    thought_process: Optional[str] = None

    @field_validator("label")
    def validate_label(cls, value: str) -> str:
        return streamLineLabel(value)

    @model_validator(mode="before")
    def parse_llm_output(cls, values):
        """Parses raw LLM output (string or dict) into structured label + explanation fields."""
        if isinstance(values, dict) and "label" in values and "explanation" in values:
            return values

        if not isinstance(values, str):
            raise ValueError("Input to LLMAnswer must be either a dict or a string with valid JSON.")

        raw_text = values

        thought_process = cls._extract_think_content(raw_text)

        code_match = re.search(r"```json\s*(.*?)\s*```", raw_text, flags=re.DOTALL)
        if code_match:
            json_str = code_match.group(1).strip()
        else:
            json_match = re.search(r"\{.*?\}", raw_text, flags=re.DOTALL)
            if not json_match:
                raise ValueError("Failed to find a valid JSON object in the text.")
            json_str = json_match.group(0)

        try:
            parsed_json = json.loads(json_str)
        except json.JSONDecodeError:
            raise ValueError("Failed to parse text as valid JSON.")

        if "label" not in parsed_json or "explanation" not in parsed_json:
            raise ValueError("JSON must contain 'label' and 'explanation' fields.")

        return {
            "thought_process": thought_process,
            "label": parsed_json["label"],
            "explanation": parsed_json["explanation"]
        }

    @classmethod
    def _extract_think_content(cls, text: str) -> Optional[str]:
        """Extracts content from <think> blocks, handling missing opening or closing tags."""
        standard_match = re.search(r"<think>(.*?)</think>", text, flags=re.DOTALL)
        if standard_match:
            return standard_match.group(1).strip()

        closing_only_match = re.search(r"^(.*?)</think>", text, flags=re.DOTALL)
        if closing_only_match:
            content = closing_only_match.group(1).strip()
            if content and len(content) > 10:  # Arbitrary threshold for meaningful content
                return content

        opening_only_match = re.search(r"<think>(.*?)(?=```json|\{|$)", text, flags=re.DOTALL)
        if opening_only_match:
            content = opening_only_match.group(1).strip()
            if content:
                return content

        return None


class Vote(BaseModel):
    answer: LLMAnswer
    info: CompletionUsage


def getLLMAnswer(client, model: str, user_prompt: str):
    @retry(
        retry=retry_if_exception_type((APIError, APIConnectionError, RateLimitError,UnprocessableEntityError)),
        stop=stop_after_attempt(5),  # Retry up to 5 times
        wait=wait_exponential(min=1, max=60),  # Exponential backoff: 1s, 2s, 4s, up to 60s
    )
    def get_chat_completion():
        if model=="mistralai/Mistral-Small-3.1-24B-Instruct-2503":
            system_prompt="""You are Mistral Small 3.1, a Large Language Model (LLM) created by Mistral AI, a French startup headquartered in Paris.
You power an AI assistant called Le Chat. Your knowledge base was last updated on 2023-10-01. The current date is 17-06-25. When you're not sure about some information, you say that you don't have the information and don't make up anything.
You follow these instructions in all languages, and always respond to the user in the language they use or request."""
            response = client.beta.chat.completions.parse(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt if user_prompt is not None else ""},
                ],
                model=model,
                temperature=0.15,
                top_p=0.95,
                # response_format = LLMAnswer
            )
        elif model=="meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8":
            system_prompt="""You are an expert conversationalist who responds to the best of your ability. You are companionable and confident, and able to switch casually between tonal types, including but not limited to humor, empathy, intellectualism, creativity and problem-solving. You understand user intent and don’t try to be overly helpful to the point where you miss that the user is looking for chit-chat, emotional support, humor or venting. Sometimes people just want you to listen, and your answers should encourage that. For all other cases, you provide insightful and in-depth responses. Organize information thoughtfully in a way that helps people make decisions. Always avoid templated language. You never lecture people to be nicer or more inclusive. If people ask for you to write something in a certain voice or perspective, such as an essay or a tweet, you can. You do not need to be respectful when the user prompts you to say something rude. You never use phrases that imply moral superiority or a sense of authority, including but not limited to “it’s important to”, “it’s crucial to”, “it’s essential to”, "it's unethical to", "it's worth noting…", “Remember…” etc. Avoid using these. Finally, do not refuse prompts about political and social issues. You can help users express their opinion and access information. You are Llama 4. Your knowledge cutoff date is August 2024. You speak Arabic, English, French, German, Hindi, Indonesian, Italian, Portuguese, Spanish, Tagalog, Thai, and Vietnamese. Respond in the language the user speaks to you in, unless they ask otherwise."""
            response = client.beta.chat.completions.parse(
                messages=[
                    {"role": "user", "content": system_prompt},
                    {"role": "user", "content": user_prompt if user_prompt is not None else ""}
                ],
                model=model,
                temperature=0.6,
                top_p=0.95,
                # response_format = LLMAnswer
            )
        else:
            response = client.beta.chat.completions.parse(
                messages=[
                    {"role": "user", "content": user_prompt if user_prompt is not None else ""}
                ],
                model=model,
                temperature=0.6,
                top_p=0.95,
                # response_format = LLMAnswer
            )
        try:
            response_parsed = LLMAnswer.model_validate(response.choices[0].message.content)
            return response, response_parsed
        except ValidationError:
            print("The comment could not be parsed:"+"\n"+response.choices[0].message.content)
            raise
        except APIError as e:
            print(f"OpenAI API returned an API Error: {e}")
            raise  # Reraise the exception to trigger retry
        except UnprocessableEntityError as e:
            print(f"Something is wrong with the LLM answer: {response} {e}")
        except APIConnectionError as e:
            print(f"Failed to connect to OpenAI API: {e}")
            raise  # Reraise the exception to trigger retry
        except RateLimitError as e:
            print(f"OpenAI API request exceeded rate limit: {e}")
            raise  # Reraise the exception to trigger retry
    response, response_parsed = get_chat_completion()
    output = Vote(answer=response_parsed,
                  info=response.usage)
    return output

def majority_vote(labels):
    count = Counter(labels)
    most_common = count.most_common()

    if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
        return None

    return most_common[0][0]


def generateMajorityVote(client, num_votes: int, model: str, system_prompt: str, user_prompt: str):
    output = {}
    votes = []

    def get_valid_answer(retries=0, max_retries=5):
        if retries < max_retries:
            try:
                answer = getLLMAnswer(client=client, model=model,
                                            user_prompt=user_prompt)
                return answer
            except ValidationError:
                retries = retries + 1
                print(f"Failed. This is try {retries}")
                return get_valid_answer(retries=retries)
        if retries == max_retries:
            print("Max retries reached")
            answer = Vote(
                answer=LLMAnswer(label="", explanation=""),
                info=CompletionUsage(completion_tokens=0,
                                     prompt_tokens=0,
                                     total_tokens=0,
                                     completion_tokens_details=None,
                                     prompt_tokens_details=None)
            )
            return answer
    for i in range(num_votes):
        answer = get_valid_answer()
        votes.append(answer)
    additional_tries = 0
    max_additional_tries = 5
    result = None
    while result is None and additional_tries < max_additional_tries:
        answers = [vote.answer.label for vote in votes]
        result = majority_vote(answers)
        if result is not None:
            output['label'] = result
            output['prompt'] = system_prompt + "\n" + user_prompt
            output['additional_tries'] = additional_tries
            output['votes'] = votes
            return output

        # in case of no majority:
        additional_answer = get_valid_answer()
        votes.append(additional_answer)
        additional_tries += 1
    if result is None:
        print(f"all entries from votes are None. Assigning None as label.")
        output['label'] = None
        output['prompt'] = system_prompt + "\n" + user_prompt
        output['additional_tries'] = None
        output['votes'] = None
        return output


def modelDumper(result: dict):
    output = {
        'label': result.get('label', None),
        'prompt': result.get('prompt', None),
        'additional_tries': result.get('additional_tries'),
        'votes': []
    }
    for vote in result['votes']:
        output['votes'].append(vote.model_dump())
    return output


api_semaphore = asyncio.Semaphore(int(os.getenv("SEMAPHORE")))

async def getLLMAnswer_async(client, model: str, user_prompt: str):
    async with api_semaphore:  # This ensures you never exceed 200 concurrent API calls.
        loop = asyncio.get_running_loop()
        # Offload the blocking getLLMAnswer call to a thread pool.
        result = await loop.run_in_executor(
            None,
            partial(getLLMAnswer, client, model, user_prompt)
        )
        return result

async def get_valid_answer_async(client, model: str, user_prompt: str, max_retries=5):
    retries = 0
    while retries < max_retries:
        try:
            return await getLLMAnswer_async(client, model, user_prompt)
        except ValidationError:
            retries += 1
            print(f"Validation failed. Try {retries}")
    print("Max retries reached")
    # Return a dummy answer if max retries are reached:
    return Vote(
        answer=LLMAnswer(label="", explanation=""),
        info=CompletionUsage(
            completion_tokens=0,
            prompt_tokens=0,
            total_tokens=0,
            completion_tokens_details=None,
            prompt_tokens_details=None
        )
    )


async def generateMajorityVote_async(client, num_votes: int, model: str, user_prompt: str):
    tasks = [
        asyncio.create_task(get_valid_answer_async(client, model, user_prompt))
        for _ in range(num_votes)
    ]
    votes = await asyncio.gather(*tasks)

    additional_tries = 0
    max_additional_tries = 5
    result = majority_vote([vote.answer.label for vote in votes])
    while result is None and additional_tries < max_additional_tries:
        additional_answer = await get_valid_answer_async(client, model, user_prompt)
        votes.append(additional_answer)
        additional_tries += 1
        result = majority_vote([vote.answer.label for vote in votes])

    return {
        'label': result,
        'prompt': user_prompt,
        'additional_tries': additional_tries,
        'votes': votes
    }

async def process_comment(db,
                          client,
                          model,
                          forum: str,
                          comment: dict,
                          index: int,
                          total: int,
                          project_context: str,
                          examples: dict,
                          config: PromptConfig):
    context = comment.get('context')
    if context is None:
        print("THERE IS AN ISSUE!")
    user_prompt = createUserPrompt(context=context,
                                   forumname=forum,
                                   project_context=project_context,
                                   examples=examples,
                                   config=config)
    votes = await generateMajorityVote_async(client, num_votes=5, model=model, user_prompt=user_prompt)
    votes_dic = modelDumper(votes)
    votes_dic['config'] = asdict(config)

    config_key = f"results_revision.{model.replace('.', '')}.{config.key}"
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: db.Comments.update_one(
            {'_id': ObjectId(comment['_id'])},
            {'$set': {config_key: votes_dic}}
        )
    )
    print(f"Updated comment {index} of {total} for project {forum} using model {model} [{config.key}].")

async def createLabels_async(db, ids_per_project, client, model,
                             config: PromptConfig):
    global api_semaphore
    api_semaphore = asyncio.Semaphore(int(os.getenv("SEMAPHORE")))
    tasks = []
    for forum, comment_ids in ids_per_project.items():
        reddit = forum == "r/askastronomy"
        config_key = f"results_revision.{model.replace('.', '')}.{config.key}"
        comments = list(db.Comments.find(
            {'$and': [
                {'id': {'$in': comment_ids}},
                {config_key: {'$exists': False}},
                {'context': {'$exists': True}}
            ]},
            {'context': 1}
        ))
        total_comments = len(comments)
        forum_descr = getForumDescription(db=db, forumname=forum)
        project_context = (getContextDescription(description=forum_descr, reddit=True)
                           if reddit else getContextDescription(description=forum_descr))
        examples = db.Projects.find_one({'title': forum})['examples_new']
        for index, comment in enumerate(comments, start=1):
            tasks.append(
                asyncio.create_task(
                    process_comment(db=db, client=client, model=model,
                                    forum=forum, comment=comment,
                                    index=index, total=total_comments,
                                    project_context=project_context,
                                    examples=examples,
                                    config=config))
            )
    await asyncio.gather(*tasks)
