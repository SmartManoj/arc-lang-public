import asyncio
import copy
import json
import os
import random
import time
import typing as T

import logfire
from anthropic import AsyncAnthropic
from devtools import debug
from google import genai
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from xai_sdk import AsyncClient as XaiAsyncClient
from xai_sdk.chat import assistant, image, system, user

from src.async_utils.semaphore_monitor import MonitoredSemaphore
from src.llms.models import Model
from src.utils import random_str

BMType = T.TypeVar("BMType", bound=BaseModel)

openai_client = AsyncOpenAI(
    api_key=os.environ["OPENAI_API_KEY"], timeout=3600, max_retries=2
)
anthropic_client = AsyncAnthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY"), timeout=2500, max_retries=2
)
deepseek_client = AsyncOpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
    timeout=2500,
    max_retries=2,
)
openrouter_client = AsyncOpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1",
    timeout=2500,
    max_retries=2,
)
gemini_client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"],
)

# Semaphore to limit concurrent API calls to 100
API_SEMAPHORE = MonitoredSemaphore(
    int(os.environ["MAX_CONCURRENCY"]),
    name="API_SEMAPHORE",
    update_url="https://jj-production.up.railway.app/api_semaphore/concurrency_limit",
    update_interval=5,
)


async def get_next_structure(
    structure: type[BMType],  # type[T]
    model: Model,
    messages: list,
) -> BMType:
    res_id = random_str(k=6)

    with logfire.span(
        "llm_call",
        model=model.value,
        structure=structure.__name__,
        request_id=res_id,
    ) as span:
        start = time.time()
        logfire.debug(
            "Starting LLM call",
            model=model.value,
            structure=structure.__name__,
            request_id=res_id,
        )

        async with API_SEMAPHORE:
            if model in [
                Model.o4_mini,
                Model.o3,
                Model.gpt_4_1,
                Model.gpt_4_1_mini,
                Model.o3_pro,
            ]:
                res = await _get_next_structure_openai(
                    structure=structure, model=model, messages=messages
                )
            elif model in [Model.sonnet_4, Model.opus_4]:
                res = await _get_next_structure_anthropic(
                    structure=structure, model=model, messages=messages
                )
            elif model in [Model.grok_4, Model.grok_3_mini_fast]:
                res = await _get_next_structure_xai(
                    structure=structure, model=model, messages=messages
                )
            elif model in [Model.deepseek_reasoner, Model.deepseek_chat]:
                res = await _get_next_structure_deepseek(
                    structure=structure, model=model, messages=messages
                )
            elif model in [Model.gemini_2_5, Model.gemini_2_5_flash_lite]:
                res = await _get_next_structure_gemini(
                    structure=structure, model=model, messages=messages
                )
            elif model in [
                Model.openrouter_sonnet_3_7_thinking,
                Model.openrouter_sonnet_3_7,
                Model.openrouter_gemini_2_5_free,
                Model.openrouter_gemini_2_5,
                Model.openrouter_deepseek_3_free,
                Model.openrouter_deepseek_r1,
                Model.openrouter_deepseek_r1_free,
                Model.openrouter_grok_v3,
                Model.openrouter_quasar_alpha,
                Model.openrouter_optimus_alpha,
                Model.openrouter_qwen_235b,
                Model.openrouter_qwen_235b_thinking,
                Model.openrouter_gemini_2_5_flash_lite,
                Model.openrouter_glm,
                Model.openrouter_kimi_k2,
                Model.openrouter_grok_4,
                Model.openrouter_horizon_alpha,
            ]:
                res = await _get_next_structure_openrouter(
                    structure=structure, model=model, messages=messages
                )
            else:
                raise Exception(f"Invalid model {model}.")

            duration = time.time() - start
            span.set_attribute("duration_seconds", duration)
            # span.set_attribute("response", res.model_dump())

            response_dump = res.model_dump()
            if "grid" in response_dump:
                del response_dump["grid"]

            logfire.debug(
                "LLM call completed",
                model=model.value,
                structure=structure.__name__,
                duration_seconds=duration,
                request_id=res_id,
                response=response_dump,
            )

            return res


async def _get_next_structure_openai(
    structure: type[BMType],  # type[T]
    model: Model,
    messages: list,
) -> BMType:
    if model in [Model.o3, Model.o4_mini, Model.o3_pro]:
        reasoning = {"effort": "high"}
    else:
        reasoning = None
    response = await openai_client.responses.parse(
        model=model.value,
        input=messages,
        text_format=structure,
        max_output_tokens=100_000,
        reasoning=reasoning,
    )
    if model in [Model.o3_pro]:
        debug(response)
    output: BMType = response.output_parsed
    return output


def update_messages_xai(messages: list[dict]) -> list:
    final_messages = []
    for message in messages:
        if message["role"] == "system":
            role = system
        elif message["role"] == "user":
            role = user
        elif message["role"] == "assistant":
            role = assistant
        else:
            raise Exception(f"invalid role in message: {message}")
        if isinstance(message["content"], list):
            for c in message["content"]:
                if c["type"] in ["input_text", "output_text"]:
                    final_messages.append(role(c["text"]))
                elif c["type"] == "input_image":
                    final_messages.append(role(image(c["image_url"])))
                else:
                    raise Exception(f"invalid content type: {c}")
        else:
            raise Exception(f"make sure content is a list!: {message}")
    return final_messages


def update_messages_anthropic(messages: list[dict]) -> list[dict]:
    messages = copy.deepcopy(messages)
    for message in messages:
        if "content" in message:
            if isinstance(message["content"], list):
                for c in message["content"]:
                    if c["type"] in ["input_text", "output_text"]:
                        c["type"] = "text"
                    if c["type"] == "input_image":
                        c["type"] = "image"
                        c["source"] = {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": c["image_url"].replace(
                                "data:image/png;base64,", ""
                            ),
                        }
                        del c["image_url"]
                        del c["detail"]
    return messages


MAX_TOKENS_ANTHROPIC_D: dict[Model:int] = {
    Model.sonnet_4: 64_000,
    Model.opus_4: 32_000,
}
MAX_TOKENS_THINKING_ANTHROPIC_D: dict[Model:int] = {
    Model.sonnet_4: 60_000,
    Model.opus_4: 30_000,
}
MAX_TOKENS_DEEPSEEK_D: dict[Model:int] = {
    Model.deepseek_chat: 8_192,
    Model.deepseek_reasoner: 32_768,
}


async def _get_next_structure_anthropic(
    structure: type[BMType],  # type[T]
    model: Model,
    messages: list,
) -> BMType:
    tool_schema = structure.model_json_schema()
    messages = update_messages_anthropic(messages=messages)
    response = await anthropic_client.messages.create(
        model=model.value,
        messages=messages,
        max_tokens=MAX_TOKENS_ANTHROPIC_D[model],
        tools=[
            {
                "name": "output_grid",
                "description": tool_schema["description"],
                "input_schema": tool_schema,
            }
        ],
        thinking={
            "type": "enabled",
            "budget_tokens": MAX_TOKENS_THINKING_ANTHROPIC_D[model],
        },
    )
    tool_call = next(block for block in response.content if block.type == "tool_use")
    tool_input = tool_call.input
    output: BMType = structure.model_validate(tool_input)
    return output


class ModelPricing(BaseModel):
    prompt_tokens: float
    reasoning_tokens: float
    completion_tokens: float


MODEL_PRICING_D: dict[Model, ModelPricing] = {
    Model.grok_4: ModelPricing(
        prompt_tokens=300 / 1_000_000,
        reasoning_tokens=1_500 / 1_000_000,
        completion_tokens=1_500 / 1_000_000,
    ),
    Model.grok_3_mini_fast: ModelPricing(
        prompt_tokens=60 / 1_000_000,
        reasoning_tokens=400 / 1_000_000,
        completion_tokens=400 / 1_000_000,
    ),
}


class GrokUsage(BaseModel):
    completion_tokens: int
    prompt_tokens: int
    total_tokens: int
    prompt_text_tokens: int
    reasoning_tokens: int
    cached_prompt_text_tokens: int

    def cents(self, model: Model) -> int:
        pricing = MODEL_PRICING_D[model]
        return round(
            self.prompt_tokens * pricing.prompt_tokens
            + self.reasoning_tokens * pricing.reasoning_tokens
            + self.completion_tokens * pricing.completion_tokens
        )


async def _get_next_structure_xai(
    structure: type[BMType],  # type[T]
    model: Model,
    messages: list,
) -> BMType:
    messages = update_messages_xai(messages=messages)

    # Configure retry policy for rate limiting
    custom_retry_policy = json.dumps(
        {
            "methodConfig": [
                {
                    "name": [{}],
                    "retryPolicy": {
                        "maxAttempts": 5,
                        "initialBackoff": "2s",
                        "maxBackoff": "120s",
                        "backoffMultiplier": 3.0,
                        "retryableStatusCodes": [
                            "UNAVAILABLE",
                            "RESOURCE_EXHAUSTED",
                            # "DEADLINE_EXCEEDED",
                        ],
                    },
                }
            ]
        }
    )

    api_keys = os.environ["XAI_API_KEY"].split(",")

    xai_client = XaiAsyncClient(
        api_key=random.choice(api_keys),
        timeout=2_000,
        channel_options=[("grpc.service_config", custom_retry_policy)],
    )
    chat = xai_client.chat.create(
        model=model.value,
        messages=messages,
        max_tokens=256_000,
        # reasoning_effort="high", # not supported for grok-4
    )
    response, struct = await chat.parse(shape=structure)
    try:
        grok_usage = GrokUsage(
            completion_tokens=response.usage.completion_tokens,
            prompt_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            prompt_text_tokens=response.usage.prompt_text_tokens,
            reasoning_tokens=response.usage.reasoning_tokens,
            cached_prompt_text_tokens=response.usage.cached_prompt_text_tokens,
        )
        logfire.debug(
            "usage",
            usage=grok_usage,
            cents=grok_usage.cents(model=model),
            finish_reason=response.finish_reason,
            reasoning_content=response.reasoning_content,
        )

    except Exception as e:
        print(f"usage error: {e=}")
        pass
    return struct


def update_messages_deepseek(
    messages: list[dict], structure: type[BMType]
) -> list[dict]:
    messages = copy.deepcopy(messages)
    schema = structure.model_json_schema()

    # Convert messages to simple format expected by DeepSeek
    final_messages = []

    # Add system message with JSON instructions
    system_content = f"""You are a helpful assistant that outputs structured JSON data.
Always output valid JSON that strictly follows this schema:
{schema}

IMPORTANT: Give the output in a valid JSON string (it should not be wrapped in markdown, just plain json object)."""

    final_messages.append({"role": "system", "content": system_content})

    for message in messages:
        if message["role"] == "system":
            # Append to our system message
            final_messages[0]["content"] += f"\n\n{message.get('content', '')}"
        else:
            if isinstance(message["content"], list):
                # Concatenate all text content
                text_parts = []
                for c in message["content"]:
                    if c["type"] in ["input_text", "output_text"]:
                        text_parts.append(c["text"])
                content = " ".join(text_parts)
            else:
                content = message["content"]

            final_messages.append({"role": message["role"], "content": content})

    return final_messages


async def _get_next_structure_deepseek(
    structure: type[BMType],  # type[T]
    model: Model,
    messages: list,
) -> BMType:
    import json

    messages = update_messages_deepseek(messages=messages, structure=structure)

    # Use JSON mode
    response = await deepseek_client.chat.completions.create(
        model=model.value,
        messages=messages,
        response_format={"type": "json_object"},
        max_tokens=MAX_TOKENS_DEEPSEEK_D[model],
        # temperature=0.3,  # Lower temperature for more consistent JSON output
    )

    # Parse the JSON response
    content = response.choices[0].message.content
    if not content:
        raise Exception("Empty response from DeepSeek model")

    try:
        json_data = json.loads(content)
        output: BMType = structure.model_validate(json_data)
        return output
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse JSON response: {e}\nResponse: {content}")


def update_messages_openrouter(
    messages: list[dict], structure: type[BMType]
) -> list[dict]:
    messages = copy.deepcopy(messages)
    schema = structure.model_json_schema()

    # Convert messages to simple format expected by OpenRouter
    final_messages = []

    # Add system message with JSON instructions
    system_content = f"""You are a helpful assistant that outputs structured JSON data.
Always output valid JSON that strictly follows this schema:
{schema}

IMPORTANT: Give the output in a valid JSON string (it should not be wrapped in markdown, just plain json object)."""

    final_messages.append({"role": "system", "content": system_content})

    for message in messages:
        if message["role"] == "system":
            # Append to our system message
            final_messages[0]["content"] += f"\n\n{message.get('content', '')}"
        else:
            if isinstance(message["content"], list):
                # Handle structured content format
                text_parts = []
                for c in message["content"]:
                    if c["type"] in ["input_text", "output_text", "text"]:
                        text_parts.append(c.get("text", c.get("content", "")))
                content = " ".join(text_parts)
            else:
                content = message["content"]

            final_messages.append({"role": message["role"], "content": content})

    return final_messages


def update_messages_gemini(messages: list[dict]) -> str:
    """Convert messages to a single prompt string for Gemini."""
    parts = []

    for message in messages:
        role = message["role"]

        if isinstance(message["content"], list):
            # Handle structured content format
            text_parts = []
            for c in message["content"]:
                if c["type"] in ["input_text", "output_text", "text"]:
                    text_parts.append(c.get("text", c.get("content", "")))
                # Note: For now, we're skipping image handling for Gemini
                # You can add image support later if needed
            content = " ".join(text_parts)
        else:
            content = message["content"]

        if role == "system":
            parts.append(f"System: {content}")
        elif role == "user":
            parts.append(f"User: {content}")
        elif role == "assistant":
            parts.append(f"Assistant: {content}")

    return "\n\n".join(parts)


async def _get_next_structure_openrouter(
    structure: type[BMType],  # type[T]
    model: Model,
    messages: list,
) -> BMType:
    import json

    messages = update_messages_openrouter(messages=messages, structure=structure)

    response_format = {"type": "json_object"}
    extra_body = {}
    if model in [Model.openrouter_qwen_235b_thinking]:
        response_format = None
        extra_body["provider"] = {
            "order": ["Novita"],
            "allow_fallbacks": True,
        }
    if model in [
        Model.openrouter_qwen_235b,
        # Model.openrouter_qwen_235b_thinking,
    ]:
        extra_body["provider"] = {
            "only": ["cerebras"],
            # "allow_fallbacks": True,
        }
    # if model in [Model.openrouter_glm]:
    #     extra_body["reasoning"]["enabled"] = True

    # Use JSON mode if supported by the model
    response = await openrouter_client.chat.completions.create(
        model=model.value,
        messages=messages,
        response_format=response_format,
        max_tokens=100_000,  # Default max tokens for OpenRouter
        # temperature=0.3,  # Lower temperature for more consistent JSON output
        extra_body=extra_body,
        # reasoning_effort="high",
    )

    # Parse the JSON response
    content = response.choices[0].message.content
    if not content:
        raise Exception("Empty response from OpenRouter model")

    try:
        json_data = json.loads(content)
        output: BMType = structure.model_validate(json_data)
        return output
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse JSON response: {e}\nResponse: {content}")


async def _get_next_structure_gemini(
    structure: type[BMType],  # type[T]
    model: Model,
    messages: list,
) -> BMType:
    # Convert messages to Gemini format
    prompt = update_messages_gemini(messages=messages)

    # Generate content with structured output
    response = await asyncio.to_thread(
        gemini_client.models.generate_content,
        model=model.value,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": structure,
        },
    )

    # The response.parsed should contain the instantiated object
    if hasattr(response, "parsed") and response.parsed:
        return response.parsed

    # Fallback to parsing the text response
    import json

    content = response.text
    if not content:
        raise Exception("Empty response from Gemini model")

    try:
        json_data = json.loads(content)
        output: BMType = structure.model_validate(json_data)
        return output
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse JSON response: {e}\nResponse: {content}")


async def main_test() -> None:
    class Reasoning(BaseModel):
        """Reasoning over a problem returning the reasoning string and the answer."""

        reasoning: str = Field(..., description="Reasoning for the math problem.")
        answer: int = Field(..., description="The answer to the math problem.")

    # test openai
    """
    response = await _get_next_structure_openai(
        structure=Reasoning,
        model=Model.o4_mini,
        messages=[
            {
                "role": "system",
                "content": "you are a math solving pirate. always talk like a pirate.",
            },
            {"role": "user", "content": "what is 39 * 28937?"},
        ],
    )
    debug(response)

    # test anthropic
    response = await _get_next_structure_anthropic(
        structure=Reasoning,
        model=Model.sonnet_4,
        messages=[
            {
                "role": "user",
                "content": "you are a math solving pirate. always talk like a pirate.",
            },
            {"role": "user", "content": "what is 39 * 28937?"},
        ],
    )
    debug(response)
    """
    # test next structure general
    response = await get_next_structure(
        structure=Reasoning,
        model=Model.grok_4,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "you are a math solving pirate. always talk like a pirate.",
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "what is 39 * 28937?"}],
            },
        ],
    )
    debug(response)

    # test deepseek
    # response = await get_next_structure(
    #     structure=Reasoning,
    #     model=Model.deepseek_chat,
    #     messages=[
    #         {
    #             "role": "system",
    #             "content": "you are a math solving pirate. always talk like a pirate.",
    #         },
    #         {"role": "user", "content": "what is 39 * 28937?"},
    #     ],
    # )
    # debug(response)

    # test openrouter
    # response = await get_next_structure(
    #     structure=Reasoning,
    #     model=Model.openrouter_qwen_235b,
    #     messages=[
    #         {
    #             "role": "system",
    #             "content": "you are a math solving pirate. always talk like a pirate.",
    #         },
    #         {"role": "user", "content": "what is 39 * 28937?"},
    #     ],
    # )
    # debug(response)

    # test gemini
    # response = await get_next_structure(
    #     structure=Reasoning,
    #     model=Model.gemini_2_5_flash_lite,
    #     messages=[
    #         {
    #             "role": "system",
    #             "content": "you are a math solving pirate. always talk like a pirate.",
    #         },
    #         {"role": "user", "content": "what is 39 * 28937?"},
    #     ],
    # )
    # debug(response)


if __name__ == "__main__":
    import asyncio

    from dotenv import load_dotenv

    load_dotenv()
    asyncio.run(main_test())
